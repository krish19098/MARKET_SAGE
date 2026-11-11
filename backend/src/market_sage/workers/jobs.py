"""Scheduled backend jobs. These run in the worker process, independent of browsers and phones."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta

import httpx

from market_sage.analysis.analyst import cutoff_datetime
from market_sage.container import Container, recommendation_from_ledger
from market_sage.core.timeutil import IST, utcnow
from market_sage.data.providers import angelone
from market_sage.learning.controlled import drift_check, run_learning_cycle, snapshot_evaluation_dataset
from market_sage.monitoring.service import token_map_for
from market_sage.portfolio.allocator import Holding, allocate
from market_sage.portfolio.risk import settings_for_mode

log = logging.getLogger("market_sage.worker")


def ingest_job(c: Container, now: datetime) -> dict:
    if c.settings.data_mode == "fixture":
        return {"skipped": "fixture mode (SYNTHETIC data is static)"}
    latest = max((c.mds.latest_session(i["id"]) or date(2000, 1, 1) for i in c.mds.instruments.all()),
                 default=None)
    start = (latest + timedelta(days=1)) if latest else now.astimezone(IST).date() - timedelta(days=400)
    end = c.mds.calendar.latest_completed_session(now)
    if start > end:
        return {"skipped": "up to date"}
    rep = c.mds.ingest_nse_eod(start, end)
    c.mds.ingest_nse_indices(start, end)
    c.mds.ingest_nse_corporate_actions(start - timedelta(days=30), end + timedelta(days=30))
    c.store.clear()
    return {"sessions": rep.sessions, "rows": rep.rows, "issues": rep.issues, "status": rep.status}


def decision_job(c: Container, cutoff: date, now: datetime, created_at: datetime | None = None,
                 provenance_extra: dict | None = None) -> dict:
    res = c.pipeline.evaluate_universe(cutoff, now, settings_for_mode(c.settings.paper_mode), created_at=created_at,
                                       provenance_extra=provenance_extra)
    alert_ids = c.monitor.announce_recommendations(res, created_at or utcnow())
    paper = paper_follow_job(c, cutoff, res.prediction_ids) if c.settings.paper_auto_follow else []
    return {"cutoff": str(cutoff), "evaluated": len(res.recommendations),
            "buy": sum(1 for r in res.recommendations if r.action == "BUY"),
            "suppressed": sum(1 for r in res.recommendations if r.suppressed), "alerts": len(alert_ids),
            "paper_intents": len(paper), "model": res.model_note}


def paper_follow_job(c: Container, cutoff: date, prediction_ids: dict[int, str]) -> list[str]:
    """Record paper-entry intents for BUYs, sized by the allocator on the configured paper capital."""
    preds = [p for p in (c.ledger.get(pid) for pid in prediction_ids.values()) if p is not None]
    recs = [recommendation_from_ledger(p) for p in preds]
    sectors = {i["id"]: i["sector"] for i in c.mds.instruments.all()}
    open_paper = c.positions.list("open", kind="paper")
    holdings = [Holding(p["symbol"], sectors.get(p["instrument_id"]), p["quantity"] * p["avg_price"]) for p in open_paper]
    committed = sum(h.market_value for h in holdings)
    alloc = allocate(c.settings.paper_capital, recs, settings_for_mode(c.settings.paper_mode), c.costs, sectors,
                     holdings=holdings, committed_capital=committed)
    out = []
    for ln in alloc.lines:
        pid = prediction_ids[ln.instrument_id]
        c.ledger.append_event(pid, "note", {"paper_intent": True, "quantity": ln.quantity, "auto": True})
        out.append(pid)
    return out


def paper_session_job(c: Container, session: date) -> dict:
    """Execute pending paper intents whose entry session is ``session`` and mark open paper positions."""
    from sqlalchemy import select

    from market_sage.db import schema as s

    entered = 0
    with c.engine.connect() as conn:
        intents = conn.execute(select(s.prediction_events).where(s.prediction_events.c.event_type == "note")).fetchall()
        fills = {r.prediction_id for r in conn.execute(select(s.paper_fills.c.prediction_id))}
    for ev in intents:
        if not ev.payload.get("paper_intent") or ev.prediction_id in fills:
            continue
        p = c.ledger.get(ev.prediction_id)
        if p is None:
            continue
        entry_session = c.mds.calendar.next_trading_day(p["data_cutoff"].astimezone(IST).date())
        if entry_session == session:
            c.paper.try_entry(p, int(ev.payload["quantity"]), session)
            entered += 1
    actions = c.paper.mark_session(session)
    return {"entered": entered, "paper_actions": len(actions)}


def post_close_job(c: Container, now: datetime | None = None) -> dict:
    now = now or utcnow()
    out: dict = {"ingest": ingest_job(c, now)}
    cutoff = c.mds.calendar.latest_completed_session(now)
    out["paper"] = paper_session_job(c, cutoff)
    out["decision"] = decision_job(c, cutoff, now)
    out["positions"] = [a.to_dict() for _, a in c.monitor.assess_all(now)]
    out["regime_alert"] = c.monitor.check_regime(cutoff, now)
    out["evaluations"] = c.evaluator.evaluate_pending(now)
    out["alert_outcomes"] = c.performance.evaluate_alerts(now)
    return out


def learning_job(c: Container, now: datetime | None = None) -> dict:
    now = now or utcnow()
    cutoff = c.mds.calendar.latest_completed_session(now)
    synthetic = c.settings.data_mode == "fixture"
    try:
        res = run_learning_cycle(c.store, c.registry, cutoff, is_synthetic=synthetic)
        out = {"candidate_id": res.candidate_id, "promoted": res.promoted, "failed": res.gate_report["failed_checks"]}
    except ValueError as exc:
        out = {"skipped": str(exc)}
    out["drift"] = drift_check(c.engine, c.registry)
    out["evaluation_dataset"] = snapshot_evaluation_dataset(c.engine, c.settings.data_dir / "evaluation")
    return out


def heartbeat_job(c: Container) -> None:
    if c.settings.heartbeat_url:
        try:
            httpx.get(c.settings.heartbeat_url, timeout=10)
        except httpx.HTTPError as exc:  # the external monitor will alert on missed pings
            log.warning("heartbeat failed: %s", exc)


async def live_session(c: Container, until: datetime) -> None:
    """Live monitoring during market hours via Angel One WebSocket (reconnect with backoff)."""
    st = c.settings
    if not (st.angel_api_key and st.angel_client_code and st.angel_pin and st.angel_totp_secret):
        log.info("live feed not configured; monitoring uses end-of-day data only")
        return
    session = angelone.AngelSession(st.angel_api_key.get_secret_value(), st.angel_client_code,
                                    st.angel_pin.get_secret_value(), st.angel_totp_secret.get_secret_value())
    provider = angelone.AngelOneProvider(session)
    master = provider.list_instruments()
    wanted = {p["symbol"] for p in c.positions.list("open")}
    cutoff = c.latest_cutoff()
    if cutoff:
        wanted |= {p["symbol"] for p in c.predictions_for_cutoff(cutoff) if p["action"] == "BUY"}
    insts = [i for i in master if i.exchange == "NSE" and i.symbol in wanted][:angelone.CAPABILITIES.max_live_subscriptions_per_connection]
    tmap = token_map_for(c.mds, angelone.PROVIDER, insts)
    backoff = 2.0
    while utcnow() < until and insts:
        try:
            await c.monitor.run_live(provider.stream(insts), tmap)
            backoff = 2.0
        except Exception as exc:  # noqa: BLE001 - outage is alerted, then retried
            log.warning("live feed error: %s", exc)
            c.monitor.feed.connected = False
            c.monitor.check_feed(utcnow(), True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)


def market_close_today(now: datetime) -> datetime:
    return datetime.combine(now.astimezone(IST).date(), time(15, 30), tzinfo=IST)


__all__ = ["cutoff_datetime", "decision_job", "heartbeat_job", "learning_job", "live_session", "market_close_today",
           "paper_session_job", "post_close_job"]
