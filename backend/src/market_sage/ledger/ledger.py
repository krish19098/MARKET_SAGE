"""Immutable prediction ledger.

Every prediction is a timestamped commitment stored once (append-only, enforced by DB triggers) and
hash-chained: ``content_hash = sha256(prev_hash || canonical_json(content))``. Later information is stored
as linked events (also chained per prediction). Corrections are new audited events — never overwrites.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
from sqlalchemy import Engine, func, insert, select, text

from market_sage.core.timeutil import ensure_utc, utcnow
from market_sage.db import schema as s

GENESIS = "0" * 64
EVENT_TYPES = {
    "price_update",
    "alert",
    "reassessment",
    "outcome",
    "user_confirmation",
    "correction",
    "paper_fill",
    "evaluation",
    "exit_recommendation",
    "note",
}
HASHED_FIELDS = [
    "id",
    "seq",
    "created_at",
    "kind",
    "instrument_id",
    "exchange",
    "symbol",
    "data_cutoff",
    "latest_data_ts",
    "data_status",
    "price_at_prediction",
    "action",
    "direction",
    "entry_low",
    "entry_high",
    "stop",
    "target1",
    "target2",
    "horizon_sessions",
    "probabilities",
    "calibration_status",
    "uncertainty",
    "evidence",
    "thesis",
    "invalidation",
    "plan",
    "model_version",
    "feature_set_version",
    "strategy_version",
    "risk_settings_version",
    "provenance",
    "parent_prediction_id",
]


def _norm(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, list | tuple):
        return [_norm(v) for v in x]
    if isinstance(x, datetime):
        return ensure_utc(x).isoformat()
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, float | np.floating):
        return None if not np.isfinite(x) else round(float(x), 10)
    return x


def canonical(obj: Any) -> str:
    return json.dumps(_norm(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev: str, content: Any) -> str:
    return hashlib.sha256((prev + canonical(content)).encode()).hexdigest()


@dataclass
class ChainProblem:
    table: str
    ref: str
    problem: str


class PredictionLedger:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _lock(self, conn: Any) -> None:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(424242)"))

    def record(self, values: dict[str, Any]) -> str:
        """Insert a new immutable prediction. ``values`` holds the table columns except id/seq/hashes."""
        pid = str(uuid.uuid4())
        with self.engine.begin() as conn:
            self._lock(conn)
            last = conn.execute(
                select(s.predictions.c.seq, s.predictions.c.content_hash).order_by(s.predictions.c.seq.desc()).limit(1)
            ).first()
            seq = 1 if last is None else int(last.seq) + 1
            prev = GENESIS if last is None else last.content_hash
            row = {
                k: _norm(v) if k in ("probabilities", "uncertainty", "evidence", "thesis", "plan", "provenance") else v
                for k, v in values.items()
            }
            row.update(id=pid, seq=seq, created_at=values.get("created_at") or utcnow())
            content = {k: row.get(k) for k in HASHED_FIELDS}
            row["prev_hash"] = prev
            row["content_hash"] = chain_hash(prev, content)
            conn.execute(insert(s.predictions).values(**row))
        return pid

    def append_event(
        self,
        prediction_id: str,
        event_type: str,
        payload: dict[str, Any],
        data_cutoff: datetime | None = None,
        created_at: datetime | None = None,
    ) -> int:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {event_type}")
        with self.engine.begin() as conn:
            self._lock(conn)
            pred = conn.execute(select(s.predictions.c.content_hash).where(s.predictions.c.id == prediction_id)).first()
            if pred is None:
                raise KeyError(prediction_id)
            last = conn.execute(
                select(s.prediction_events.c.content_hash)
                .where(s.prediction_events.c.prediction_id == prediction_id)
                .order_by(s.prediction_events.c.id.desc())
                .limit(1)
            ).scalar()
            prev = last or pred.content_hash
            ts = created_at or utcnow()
            content = {
                "prediction_id": prediction_id,
                "event_type": event_type,
                "created_at": ts,
                "data_cutoff": data_cutoff,
                "payload": payload,
            }
            res = conn.execute(
                insert(s.prediction_events).values(
                    prediction_id=prediction_id,
                    created_at=ts,
                    event_type=event_type,
                    data_cutoff=data_cutoff,
                    payload=_norm(payload),
                    prev_hash=prev,
                    content_hash=chain_hash(prev, content),
                )
            )
            return int(res.inserted_primary_key[0])  # type: ignore[index]

    def correct(self, prediction_id: str, field: str, corrected_value: Any, reason: str, actor: str = "system") -> int:
        """Audited correction: original remains untouched; the correction is a linked event."""
        return self.append_event(
            prediction_id,
            "correction",
            {"field": field, "corrected_value": corrected_value, "reason": reason, "actor": actor},
        )

    def get(self, prediction_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(s.predictions).where(s.predictions.c.id == prediction_id)).first()
            if row is None:
                return None
            events = conn.execute(
                select(s.prediction_events)
                .where(s.prediction_events.c.prediction_id == prediction_id)
                .order_by(s.prediction_events.c.id)
            ).fetchall()
        d = dict(row._mapping)
        d["events"] = [dict(e._mapping) for e in events]
        return d

    def count(self) -> int:
        with self.engine.connect() as conn:
            return int(conn.execute(select(func.count()).select_from(s.predictions)).scalar() or 0)

    def verify(self) -> list[ChainProblem]:
        """Recompute the prediction chain and every event chain; report any mismatch (tamper evidence)."""
        problems: list[ChainProblem] = []
        with self.engine.connect() as conn:
            preds = conn.execute(select(s.predictions).order_by(s.predictions.c.seq)).fetchall()
            prev = GENESIS
            hashes = {}
            for p in preds:
                d = dict(p._mapping)
                if d["prev_hash"] != prev:
                    problems.append(ChainProblem("predictions", d["id"], "broken link to previous prediction"))
                if chain_hash(d["prev_hash"], {k: d.get(k) for k in HASHED_FIELDS}) != d["content_hash"]:
                    problems.append(ChainProblem("predictions", d["id"], "content hash mismatch"))
                prev = d["content_hash"]
                hashes[d["id"]] = d["content_hash"]
            events = conn.execute(select(s.prediction_events).order_by(s.prediction_events.c.id)).fetchall()
        last_by_pred: dict[str, str] = {}
        for e in events:
            d = dict(e._mapping)
            expected_prev = last_by_pred.get(d["prediction_id"], hashes.get(d["prediction_id"], ""))
            if d["prev_hash"] != expected_prev:
                problems.append(ChainProblem("prediction_events", str(d["id"]), "broken event link"))
            content = {
                "prediction_id": d["prediction_id"],
                "event_type": d["event_type"],
                "created_at": d["created_at"],
                "data_cutoff": d["data_cutoff"],
                "payload": d["payload"],
            }
            if chain_hash(d["prev_hash"], content) != d["content_hash"]:
                problems.append(ChainProblem("prediction_events", str(d["id"]), "event hash mismatch"))
            last_by_pred[d["prediction_id"]] = d["content_hash"]
        return problems
