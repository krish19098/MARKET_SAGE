"""Alert store: append-only alerts with stage semantics, deduplication and cooldowns.

Stages: ``early_warning`` (developing, not confirmed) | ``approaching`` (near a defined level) |
``confirmed`` (pre-defined condition occurred) | ``info``. A completed event is never labelled a prediction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Engine, and_, insert, select

from market_sage.core.timeutil import utcnow
from market_sage.db import schema as s

ALERT_CLASSES = {
    "new_buy": "New BUY opportunity",
    "early_bullish": "Early bullish development",
    "early_bearish": "Early bearish development",
    "thesis_deterioration": "Early deterioration of an active thesis",
    "approaching_entry": "Approaching entry trigger",
    "approaching_stop": "Approaching stop/invalidation",
    "stop_triggered": "Confirmed stop/exit trigger",
    "target_hit": "Target achieved",
    "partial_profit": "Partial-profit / trailing-stop suggestion",
    "regime_change": "Market/sector regime change",
    "corporate_event": "Material corporate event",
    "data_stale": "Data-provider failure or stale feed",
}
STAGES = {"early_warning", "approaching", "confirmed", "info"}
DEFAULT_COOLDOWN = timedelta(hours=20)


@dataclass(frozen=True)
class AlertDraft:
    alert_class: str
    stage: str
    title: str
    message: str
    dedupe_key: str
    instrument_id: int | None = None
    symbol: str | None = None
    prediction_id: str | None = None
    position_id: int | None = None
    data_cutoff: datetime | None = None
    probability: float | None = None
    evidence: dict[str, Any] | None = None
    invalidation: str | None = None

    def __post_init__(self) -> None:
        if self.alert_class not in ALERT_CLASSES:
            raise ValueError(f"unknown alert class {self.alert_class}")
        if self.stage not in STAGES:
            raise ValueError(f"unknown stage {self.stage}")


class AlertStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, d: AlertDraft, now: datetime | None = None, cooldown: timedelta = DEFAULT_COOLDOWN) -> int | None:
        """Insert unless an alert with the same dedupe key exists within the cooldown. Returns id or None."""
        now = now or utcnow()
        t = s.alerts
        with self.engine.begin() as conn:
            recent = conn.execute(select(t.c.id).where(and_(t.c.dedupe_key == d.dedupe_key,
                                                            t.c.created_at >= now - cooldown))).first()
            if recent is not None:
                return None
            res = conn.execute(insert(t).values(
                created_at=now, alert_class=d.alert_class, stage=d.stage, instrument_id=d.instrument_id,
                symbol=d.symbol, prediction_id=d.prediction_id, position_id=d.position_id, title=d.title,
                message=d.message, data_cutoff=d.data_cutoff, probability=d.probability, evidence=d.evidence,
                invalidation=d.invalidation, dedupe_key=d.dedupe_key))
            return int(res.inserted_primary_key[0])  # type: ignore[index]

    def record_outcome(self, alert_id: int, outcome: str, event_time: datetime | None, detail: dict | None = None) -> None:
        with self.engine.begin() as conn:
            conn.execute(insert(s.alert_outcomes).values(alert_id=alert_id, recorded_at=utcnow(), outcome=outcome,
                                                         event_time=event_time, detail=detail or {}))

    def recent(self, limit: int = 100, position_id: int | None = None) -> list[dict]:
        t = s.alerts
        q = select(t).order_by(t.c.created_at.desc(), t.c.id.desc()).limit(limit)
        if position_id is not None:
            q = q.where(t.c.position_id == position_id)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]
