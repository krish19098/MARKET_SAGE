"""Paper trading (the only execution venue in MARKET SAGE — real-money execution does not exist).

Daily-bar simulation with realistic rules: entry only if the next session trades inside the entry range
(no chasing gaps: limit at the top of the range), stops fill at the worse of stop/open on gaps, 50% booked
at Target 1 with the stop trailed to entry, remainder at Target 2, time stop at the end of the horizon range.
Costs (incl. slippage) from the cost model. All fills are recorded append-only.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Engine, insert, select

from market_sage.core.timeutil import utcnow
from market_sage.data.service import MarketDataService
from market_sage.db import schema as s
from market_sage.ledger.ledger import PredictionLedger
from market_sage.monitoring.positions import PositionRepo
from market_sage.portfolio.costs import CostModel


class PaperBroker:
    venue = "paper"

    def __init__(self, engine: Engine, mds: MarketDataService, ledger: PredictionLedger, costs: CostModel) -> None:
        self.engine, self.mds, self.ledger, self.costs = engine, mds, ledger, costs
        self.positions = PositionRepo(engine)

    def _fill(self, **v: Any) -> int:
        with self.engine.begin() as conn:
            res = conn.execute(insert(s.paper_fills).values(created_at=utcnow(), **v))
            return int(res.inserted_primary_key[0])  # type: ignore[index]

    def try_entry(self, pred: dict, quantity: int, session: date) -> int | None:
        """Simulate the entry on ``session`` (the session after the decision). Returns position id or None."""
        bars = self.mds.daily_bars(pred["instrument_id"])
        row = bars[bars["session_date"] == session]
        if row.empty:
            return None
        b = row.iloc[0]
        eh = pred["entry_high"]
        if b["open"] <= eh:
            px, why = float(b["open"]), "filled at open inside entry range"
        elif b["low"] <= eh:
            px, why = float(eh), "limit filled at top of entry range"
        else:
            self._fill(prediction_id=pred["id"], instrument_id=pred["instrument_id"], side="BUY", quantity=quantity,
                       requested_price=eh, status="missed", reason="opened and stayed above entry range (no chasing)",
                       fill_ts=b["source_ts"])
            self.ledger.append_event(pred["id"], "paper_fill", {"status": "missed", "session": str(session)})
            return None
        cost = self.costs.leg("buy", px, quantity).total
        pid = self.positions.open(kind="paper", instrument_id=pred["instrument_id"], exchange=pred["exchange"],
                                  symbol=pred["symbol"], quantity=quantity, avg_price=px, opened_at=b["source_ts"],
                                  entry_costs=cost, stop=pred["stop"], target1=pred["target1"], target2=pred["target2"],
                                  source_prediction_id=pred["id"], notes="SIMULATED paper position")
        self._fill(prediction_id=pred["id"], position_id=pid, instrument_id=pred["instrument_id"], side="BUY",
                   quantity=quantity, requested_price=eh, fill_price=px, fill_ts=b["source_ts"], costs=cost,
                   status="filled", reason=why)
        self.ledger.append_event(pred["id"], "paper_fill", {"status": "filled", "price": px, "qty": quantity,
                                                            "position_id": pid})
        return pid

    def mark_session(self, session: date, max_hold_sessions: int = 10) -> list[dict]:
        """Apply stop/target/time rules to open paper positions using the bar of ``session``."""
        actions = []
        for pos in self.positions.list("open", kind="paper"):
            bars = self.mds.daily_bars(pos["instrument_id"])
            held = bars[(bars["session_date"] > pos["opened_at"].date()) & (bars["session_date"] <= session)]
            row = bars[bars["session_date"] == session]
            if row.empty or held.empty:
                continue
            b = row.iloc[0]
            stop, t1, t2 = pos["stop"], pos["target1"], pos["target2"]
            exit_px, reason = None, None
            if stop is not None and b["low"] <= stop:
                exit_px, reason = float(min(b["open"], stop)), "stop"
            elif t1 is not None and pos["monitor_state"] != "target1_hit" and b["high"] >= t1:
                half = pos["quantity"] // 2
                if half >= 1:
                    self._record_exit(pos, half, float(max(b["open"], t1)), "target1 partial", b["source_ts"])
                    with self.engine.begin() as conn:
                        conn.execute(s.positions.update().where(s.positions.c.id == pos["id"]).values(
                            quantity=pos["quantity"] - half, stop=pos["avg_price"], monitor_state="target1_hit"))
                    actions.append({"position_id": pos["id"], "action": "partial", "price": t1})
                    continue
                exit_px, reason = float(max(b["open"], t1)), "target1"
            elif t2 is not None and b["high"] >= t2:
                exit_px, reason = float(max(b["open"], t2)), "target2"
            elif len(held) >= max_hold_sessions:
                exit_px, reason = float(b["close"]), "time stop"
            if exit_px is not None:
                self._record_exit(pos, pos["quantity"], exit_px, reason or "exit", b["source_ts"])
                actions.append({"position_id": pos["id"], "action": "exit", "price": exit_px, "reason": reason})
        return actions

    def _record_exit(self, pos: dict, qty: int, px: float, reason: str, ts: datetime) -> None:
        cost = self.costs.leg("sell", px, qty).total
        self._fill(prediction_id=pos["source_prediction_id"], position_id=pos["id"], instrument_id=pos["instrument_id"],
                   side="SELL", quantity=qty, requested_price=px, fill_price=px, fill_ts=ts, costs=cost,
                   status="filled", reason=reason)
        if qty >= pos["quantity"]:
            self.positions.close(pos["id"], px, cost, ts)
        if pos["source_prediction_id"]:
            self.ledger.append_event(pos["source_prediction_id"], "paper_fill",
                                     {"side": "SELL", "price": px, "qty": qty, "reason": reason})

    def fills(self, limit: int = 200) -> list[dict]:
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(select(s.paper_fills).order_by(s.paper_fills.c.id.desc())
                                                           .limit(limit))]
