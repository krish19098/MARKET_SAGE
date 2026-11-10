"""FastAPI application: REST + WebSocket for the five-screen PWA, and static PWA hosting.

All analysis and monitoring run in the backend worker; this API only reads state, accepts user inputs
(positions, budgets, push subscriptions) and runs on-demand analysis. Real-money execution does not exist.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import insert, select, text

from market_sage import __version__
from market_sage.api.auth import COOKIE, issue_token, require_user, verify_login
from market_sage.container import Container, recommendation_from_ledger
from market_sage.core.config import Settings, get_settings
from market_sage.core.timeutil import IST, ist_iso, utcnow
from market_sage.data.models import DataStatus
from market_sage.db import schema as s
from market_sage.learning.controlled import drift_check
from market_sage.portfolio.allocator import Holding, allocate
from market_sage.portfolio.risk import settings_for_mode


def j(x: Any) -> Any:
    """JSON-safe conversion; datetimes rendered in IST (display convention)."""
    if isinstance(x, dict):
        return {str(k): j(v) for k, v in x.items()}
    if isinstance(x, list | tuple | set):
        return [j(v) for v in x]
    if isinstance(x, datetime):
        return ist_iso(x)
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, float | np.floating):
        return None if not np.isfinite(x) else float(x)
    return x


class LoginIn(BaseModel):
    username: str
    password: str
    totp: str | None = None


class InvestIn(BaseModel):
    capital: float = Field(gt=0, le=1e9)
    mode: str = Field(default="balanced", pattern="^(balanced|growth)$")


class PositionIn(BaseModel):
    symbol: str
    exchange: str = "NSE"
    quantity: int = Field(gt=0)
    avg_price: float = Field(gt=0)
    opened_on: date | None = None
    costs: float = Field(default=0.0, ge=0)
    stop: float | None = Field(default=None, gt=0)
    target1: float | None = Field(default=None, gt=0)
    target2: float | None = Field(default=None, gt=0)
    prediction_id: str | None = None
    notes: str | None = None


class CloseIn(BaseModel):
    exit_price: float = Field(gt=0)
    costs: float = Field(default=0.0, ge=0)


class PaperFollowIn(BaseModel):
    quantity: int = Field(gt=0)


class PushSubIn(BaseModel):
    endpoint: str
    keys: dict[str, str]


def create_app(container: Container | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.c = container or Container.build(settings)
        yield

    app = FastAPI(title="MARKET SAGE", version=__version__, lifespan=lifespan,
                  description="Advisory decision support and paper trading. No real-money execution.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    app.state.settings = settings
    if container is not None:
        app.state.c = container

    def C(request: Request) -> Container:  # noqa: N802
        return request.app.state.c

    # --- public -------------------------------------------------------------------------------
    @app.get("/api/health")
    def health(request: Request) -> dict:
        c = C(request)
        with c.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "version": __version__, "execution_mode": settings.execution_mode,
                "time_ist": ist_iso(utcnow())}

    @app.post("/api/auth/login")
    def login(body: LoginIn, response: Response) -> dict:
        if settings.auth_password_hash is None:
            raise HTTPException(503, "authentication not configured: set MARKET_SAGE_AUTH_PASSWORD_HASH")
        if not verify_login(settings, body.username, body.password, body.totp):
            raise HTTPException(401, "invalid credentials")
        response.set_cookie(COOKIE, issue_token(settings), httponly=True, samesite="strict",
                            secure=settings.env == "prod", max_age=settings.jwt_ttl_minutes * 60)
        return {"ok": True, "user": settings.auth_username, "totp_required": settings.auth_totp_secret is not None}

    @app.post("/api/auth/logout")
    def logout(response: Response) -> dict:
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(user: str = Depends(require_user)) -> dict:
        return {"user": user}

    # --- Home ---------------------------------------------------------------------------------
    @app.get("/api/home")
    def home(request: Request, user: str = Depends(require_user)) -> Any:
        c = C(request)
        now = utcnow()
        st = c.mds.calendar.session_state(now)
        cutoff = c.latest_cutoff()
        preds = c.predictions_for_cutoff(cutoff) if cutoff else []
        buys = sorted([p for p in preds if p["action"] == "BUY"],
                      key=lambda p: -((p.get("uncertainty") or {}).get("expected_value_per_share") or 0))
        statuses = [p["data_status"] for p in preds]
        positions = _positions_view(c, now)
        regime = next((e for p in preds[:1] for e in p["evidence"] if e["category"] == "context"
                       and e["kind"] == "estimate"), None)
        mctx = c.pipeline.model_ctx()
        risks = []
        if any(x == DataStatus.STALE.value for x in statuses):
            risks.append({"level": "high", "text": "Some market data is stale — affected recommendations are suppressed."})
        if any(x == DataStatus.SYNTHETIC.value for x in statuses):
            risks.append({"level": "info", "text": "SYNTHETIC development data in use — not real market data."})
        if not mctx.has_skill:
            risks.append({"level": "medium", "text": f"No validated predictive edge: {mctx.skill_note}."})
        if not c.costs.verified:
            risks.append({"level": "info", "text": "Cost estimates use an unverified charge schedule."})
        if not st.verified:
            risks.append({"level": "info", "text": "Exchange holiday calendar for this year is not verified."})
        return j({
            "market": {"phase": st.phase, "trading_day": st.trading_day, "calendar_verified": st.verified,
                       "time_ist": now, "regime": regime["statement"] if regime else "unknown",
                       "latest_cutoff": cutoff, "data_status": max(set(statuses), key=statuses.count) if statuses else "none",
                       "feed": c.monitor.feed.snapshot(now)},
            "portfolio": positions["summary"],
            "opportunities": [_pred_card(p) for p in buys[:5]],
            "alerts": c.alerts.recent(8),
            "risks": risks,
            "model": {"has_skill": mctx.has_skill, "note": mctx.skill_note},
        })

    # --- Invest -------------------------------------------------------------------------------
    @app.post("/api/invest")
    def invest(body: InvestIn, request: Request, user: str = Depends(require_user)) -> Any:
        c = C(request)
        cutoff = c.latest_cutoff()
        if cutoff is None:
            raise HTTPException(409, "no recommendations recorded yet — run the end-of-day pipeline first")
        preds = c.predictions_for_cutoff(cutoff)
        recs = [recommendation_from_ledger(p) for p in preds]
        sectors = {i["id"]: i["sector"] for i in c.mds.instruments.all()}
        holdings = [Holding(p["symbol"], sectors.get(p["instrument_id"]), p["quantity"] * p["avg_price"])
                    for p in c.positions.list("open")]
        alloc = allocate(body.capital, recs, settings_for_mode(body.mode), c.costs, sectors, holdings=holdings)
        pid_by_iid = {p["instrument_id"]: p["id"] for p in preds}
        out = alloc.to_dict()
        for ln in out["lines"]:
            ln["prediction_id"] = pid_by_iid.get(ln["instrument_id"])
        out["cutoff"] = cutoff
        out["advisory"] = "Advisory recommendations for paper trading. MARKET SAGE never places orders."
        return j(out)

    @app.get("/api/opportunities")
    def opportunities(request: Request, user: str = Depends(require_user)) -> Any:
        c = C(request)
        cutoff = c.latest_cutoff()
        preds = c.predictions_for_cutoff(cutoff) if cutoff else []
        order = {"BUY": 0, "HOLD": 1, "AVOID": 2, "EXIT": 3}
        return j({"cutoff": cutoff, "items": [_pred_card(p) for p in sorted(preds, key=lambda p: order.get(p["action"], 9))]})

    # --- My Trades ----------------------------------------------------------------------------
    @app.get("/api/positions")
    def positions(request: Request, user: str = Depends(require_user)) -> Any:
        return j(_positions_view(C(request), utcnow()))

    @app.post("/api/positions")
    def add_position(body: PositionIn, request: Request, user: str = Depends(require_user)) -> Any:
        c = C(request)
        inst = c.mds.instruments.by_symbol(body.exchange.upper(), body.symbol.upper())
        if inst is None:
            raise HTTPException(404, f"unknown instrument {body.exchange}:{body.symbol}")
        opened = (datetime.combine(body.opened_on, datetime.min.time(), tzinfo=IST) if body.opened_on else utcnow())
        pid = c.positions.open(kind="actual", instrument_id=inst["id"], exchange=inst["exchange"], symbol=inst["symbol"],
                               quantity=body.quantity, avg_price=body.avg_price, opened_at=opened,
                               entry_costs=body.costs, stop=body.stop, target1=body.target1, target2=body.target2,
                               source_prediction_id=body.prediction_id, notes=body.notes)
        if body.prediction_id:
            c.ledger.append_event(body.prediction_id, "user_confirmation",
                                  {"position_id": pid, "fill_price": body.avg_price, "quantity": body.quantity,
                                   "kind": "actual"})
        _audit(c, "position_added", {"position_id": pid, "symbol": inst["symbol"]})
        return j(c.positions.get(pid))

    @app.post("/api/positions/{position_id}/close")
    def close_position(position_id: int, body: CloseIn, request: Request, user: str = Depends(require_user)) -> Any:
        c = C(request)
        pos = c.positions.get(position_id)
        if pos is None or pos["status"] != "open":
            raise HTTPException(404, "open position not found")
        if pos["kind"] != "actual":
            raise HTTPException(400, "paper positions are closed by the simulator")
        c.positions.close(position_id, body.exit_price, body.costs)
        if pos["source_prediction_id"]:
            c.ledger.append_event(pos["source_prediction_id"], "user_confirmation",
                                  {"position_id": position_id, "exit_fill": body.exit_price, "kind": "actual_exit"})
        _audit(c, "position_closed", {"position_id": position_id})
        return j(c.positions.get(position_id))

    @app.get("/api/positions/{position_id}/assessment")
    def assessment(position_id: int, request: Request, user: str = Depends(require_user)) -> Any:
        c = C(request)
        pos = c.positions.get(position_id)
        if pos is None:
            raise HTTPException(404, "position not found")
        st = c.mds.calendar.session_state(utcnow())
        a = c.monitor.assess_one(pos, utcnow(), st.phase == "open")
        return j(a.to_dict() | {"alerts": c.alerts.recent(20, position_id=position_id)})

    @app.post("/api/paper/follow/{prediction_id}")
    def paper_follow(prediction_id: str, body: PaperFollowIn, request: Request, user: str = Depends(require_user)) -> Any:
        c = C(request)
        p = c.ledger.get(prediction_id)
        if p is None or p["action"] != "BUY":
            raise HTTPException(404, "BUY prediction not found")
        c.ledger.append_event(prediction_id, "note", {"paper_intent": True, "quantity": body.quantity})
        return {"ok": True, "message": "Paper entry will be simulated on the next session's data (no real order)."}

    # --- Analyst ------------------------------------------------------------------------------
    @app.get("/api/instruments")
    def instruments(request: Request, q: str = "", user: str = Depends(require_user)) -> Any:
        c = C(request)
        qq = q.upper()
        rows = [i for i in c.mds.instruments.all() if qq in i["symbol"] or qq in (i["name"] or "").upper()]
        return j([{"id": i["id"], "symbol": i["symbol"], "exchange": i["exchange"], "name": i["name"],
                   "sector": i["sector"], "is_index": i["is_index"]} for i in rows[:50]])

    @app.get("/api/analyst/{exchange}/{symbol}")
    def analyst(exchange: str, symbol: str, request: Request, user: str = Depends(require_user)) -> Any:
        c = C(request)
        inst = c.mds.instruments.by_symbol(exchange.upper(), symbol.upper())
        if inst is None:
            raise HTTPException(404, "unknown instrument")
        latest = c.mds.latest_session(inst["id"])
        if latest is None:
            raise HTTPException(409, "no data for instrument")
        now = utcnow()
        rec = c.pipeline.evaluate(inst["id"], latest, now, settings_for_mode("balanced"))
        f = c.store.instrument_features(inst["id"], until=latest).tail(250)
        with c.engine.connect() as conn:
            hist = conn.execute(select(s.predictions.c.id, s.predictions.c.created_at, s.predictions.c.action,
                                       s.predictions.c.price_at_prediction, s.predictions.c.stop, s.predictions.c.target1)
                                .where(s.predictions.c.instrument_id == inst["id"])
                                .order_by(s.predictions.c.seq.desc()).limit(20)).fetchall()
        chart = [{"t": d.isoformat(), "o": o, "h": h, "l": lo, "c": cl, "v": v, "sma20": s20, "sma50": s50}
                 for d, o, h, lo, cl, v, s20, s50 in zip(
                     f["session_date"], f["open"], f["high"], f["low"], f["close"], f["volume"],
                     f["close"] / (1 + f["c_sma20"]), f["close"] / (1 + f["c_sma50"]), strict=True)]
        out: dict[str, Any] = {"instrument": inst, "latest_session": latest, "chart": chart,
                               "history": [dict(h._mapping) for h in hist],
                               "note": "On-demand analysis (not recorded). Recorded predictions are listed under history."}
        if rec is not None:
            rep = rec.report
            out.update({"action": rec.action, "reasons": rec.reasons, "plan": rec.plan.to_dict() if rec.plan else None,
                        "probabilities": rec.probabilities, "calibration_status": rec.calibration_status,
                        "data_status": rec.data_status, "evidence": [e.to_dict() for e in rec.evidence],
                        "thesis": rec.thesis, "setups": [x.to_dict() for x in rec.setups],
                        "structure": rep.structure if rep else None, "patterns": rep.patterns if rep else [],
                        "regime": rep.regime if rep else None,
                        "analogues": rep.analogues.to_dict() if rep and rep.analogues else None,
                        "liquidity": rec.liquidity})
        return j(out)

    @app.get("/api/predictions/{prediction_id}")
    def prediction(prediction_id: str, request: Request, user: str = Depends(require_user)) -> Any:
        c = C(request)
        p = c.ledger.get(prediction_id)
        if p is None:
            raise HTTPException(404, "prediction not found")
        with c.engine.connect() as conn:
            evs = [dict(r._mapping) for r in conn.execute(select(s.evaluations).where(
                s.evaluations.c.prediction_id == prediction_id))]
            les = [dict(r._mapping) for r in conn.execute(select(s.lessons).where(s.lessons.c.prediction_id == prediction_id))]
        return j(p | {"evaluations": evs, "lessons": les})

    # --- Performance --------------------------------------------------------------------------
    @app.get("/api/performance")
    def performance(request: Request, user: str = Depends(require_user)) -> Any:
        c = C(request)
        summ = c.performance.summary()
        summ["drift"] = drift_check(c.engine, c.registry)
        summ["ledger_integrity"] = {"problems": [p.__dict__ for p in c.ledger.verify()[:20]], "predictions": c.ledger.count()}
        return j(summ)

    # --- Alerts & push ------------------------------------------------------------------------
    @app.get("/api/alerts")
    def alerts(request: Request, limit: int = 100, user: str = Depends(require_user)) -> Any:
        return j(C(request).alerts.recent(min(limit, 500)))

    @app.get("/api/push/public-key")
    def push_key(user: str = Depends(require_user)) -> dict:
        return {"publicKey": settings.vapid_public_key, "enabled": settings.vapid_public_key is not None}

    @app.post("/api/push/subscribe")
    def push_subscribe(body: PushSubIn, request: Request, user: str = Depends(require_user)) -> dict:
        c = C(request)
        with c.engine.begin() as conn:
            exists = conn.execute(select(s.push_subscriptions.c.id).where(
                s.push_subscriptions.c.endpoint == body.endpoint)).first()
            if exists is None:
                conn.execute(insert(s.push_subscriptions).values(endpoint=body.endpoint, keys=body.keys,
                                                                 user_agent=request.headers.get("user-agent"),
                                                                 created_at=utcnow(), active=True))
            else:
                conn.execute(s.push_subscriptions.update().where(s.push_subscriptions.c.id == exists.id)
                             .values(keys=body.keys, active=True))
        return {"ok": True}

    @app.websocket("/api/ws")
    async def ws(websocket: WebSocket) -> None:
        try:
            require_user(websocket)  # type: ignore[arg-type]
        except HTTPException:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        c: Container = websocket.app.state.c
        last_id = 0
        try:
            while True:
                fresh = [a for a in c.alerts.recent(20) if a["id"] > last_id]
                if fresh:
                    last_id = max(a["id"] for a in fresh)
                await websocket.send_json(j({"type": "tick", "time_ist": utcnow(), "alerts": fresh,
                                             "feed": c.monitor.feed.snapshot(utcnow())}))
                await asyncio.sleep(5)
        except WebSocketDisconnect:
            return

    # --- PWA static hosting ---------------------------------------------------------------------
    web_dir = Path(os.environ.get("MARKET_SAGE_WEB_DIR", Path(__file__).resolve().parents[4] / "frontend" / "dist"))
    if web_dir.exists():
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> Response:
            if path.startswith("api/"):
                return JSONResponse({"detail": "not found"}, status_code=404)
            target = (web_dir / path).resolve()
            if path and target.is_file() and web_dir.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(web_dir / "index.html")

    return app


def _pred_card(p: dict) -> dict:
    plan = p.get("plan") or {}
    return {"prediction_id": p["id"], "symbol": p["symbol"], "exchange": p["exchange"], "action": p["action"],
            "kind": p["kind"], "price": p["price_at_prediction"], "entry_low": p["entry_low"],
            "entry_high": p["entry_high"], "stop": p["stop"], "target1": p["target1"], "target2": p["target2"],
            "probabilities": p["probabilities"], "calibration_status": p["calibration_status"],
            "data_status": p["data_status"], "created_at": p["created_at"], "data_cutoff": p["data_cutoff"],
            "reasons": plan.get("reasons", []), "reward_risk": plan.get("reward_risk_t1"),
            "expected_value_per_share": (p.get("uncertainty") or {}).get("expected_value_per_share"),
            "setups": plan.get("setups", [])}


def _positions_view(c: Container, now: datetime) -> dict:
    out, value, cost, upnl = [], 0.0, 0.0, 0.0
    market_open = c.mds.calendar.session_state(now).phase == "open"
    for p in c.positions.list("open"):
        price, status, ts = c.monitor.price_for(p["instrument_id"], now, market_open)
        mv = price * p["quantity"] if np.isfinite(price) else 0.0
        pnl = mv - p["avg_price"] * p["quantity"] - p["entry_costs"]
        value += mv
        cost += p["avg_price"] * p["quantity"]
        upnl += pnl
        out.append(p | {"current_price": price, "price_status": status, "price_ts": ts, "market_value": mv,
                        "unrealized_pnl": pnl, "fill_type": "ACTUAL (user-confirmed)" if p["kind"] == "actual"
                        else "SIMULATED (paper)", "latest_alert": next(iter(c.alerts.recent(1, position_id=p["id"])), None)})
    closed = c.positions.list("closed")[:50]
    return {"open": out, "closed": closed,
            "summary": {"open_positions": len(out), "market_value": value, "cost_basis": cost, "unrealized_pnl": upnl,
                        "actual": sum(1 for p in out if p["kind"] == "actual"),
                        "paper": sum(1 for p in out if p["kind"] == "paper")}}


def _audit(c: Container, action: str, detail: dict) -> None:
    with c.engine.begin() as conn:
        conn.execute(insert(s.audit_log).values(ts=utcnow(), actor="owner", action=action, detail=detail))


app = create_app()
