"""Positions: user-entered actual fills vs simulated paper positions (always distinguished)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Engine, insert, select

from market_sage.core.timeutil import utcnow
from market_sage.db import schema as s

KINDS = {"actual", "paper"}


class PositionRepo:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def open(self, *, kind: str, instrument_id: int, exchange: str, symbol: str, quantity: int, avg_price: float,
             opened_at: datetime | None = None, entry_costs: float = 0.0, stop: float | None = None,
             target1: float | None = None, target2: float | None = None, source_prediction_id: str | None = None,
             notes: str | None = None) -> int:
        if kind not in KINDS:
            raise ValueError("kind must be 'actual' (user-confirmed fill) or 'paper' (simulated)")
        if quantity <= 0 or avg_price <= 0:
            raise ValueError("quantity and price must be positive")
        with self.engine.begin() as conn:
            res = conn.execute(insert(s.positions).values(
                kind=kind, instrument_id=instrument_id, exchange=exchange, symbol=symbol, quantity=quantity,
                avg_price=avg_price, opened_at=opened_at or utcnow(), entry_costs=entry_costs, stop=stop,
                target1=target1, target2=target2, source_prediction_id=source_prediction_id, status="open",
                notes=notes, monitor_state="normal"))
            return int(res.inserted_primary_key[0])  # type: ignore[index]

    def close(self, position_id: int, exit_price: float, exit_costs: float = 0.0, closed_at: datetime | None = None
              ) -> None:
        with self.engine.begin() as conn:
            conn.execute(s.positions.update().where(s.positions.c.id == position_id).values(
                status="closed", exit_price=exit_price, exit_costs=exit_costs, closed_at=closed_at or utcnow()))

    def set_state(self, position_id: int, state: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(s.positions.update().where(s.positions.c.id == position_id).values(monitor_state=state))

    def update_levels(self, position_id: int, **levels: float | None) -> None:
        allowed = {k: v for k, v in levels.items() if k in ("stop", "target1", "target2")}
        with self.engine.begin() as conn:
            conn.execute(s.positions.update().where(s.positions.c.id == position_id).values(**allowed))

    def get(self, position_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            r = conn.execute(select(s.positions).where(s.positions.c.id == position_id)).first()
        return dict(r._mapping) if r else None

    def list(self, status: str | None = "open", kind: str | None = None) -> list[dict[str, Any]]:
        q = select(s.positions).order_by(s.positions.c.opened_at.desc())
        if status:
            q = q.where(s.positions.c.status == status)
        if kind:
            q = q.where(s.positions.c.kind == kind)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]
