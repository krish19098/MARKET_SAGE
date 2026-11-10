"""Versioned model artefacts, registry status and rollback."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import Engine, and_, insert, select

from market_sage.core.timeutil import utcnow
from market_sage.db import schema as s
from market_sage.models.calibration import CLASSES, IsotonicMulticlass
from market_sage.models.estimators import Estimator


@dataclass
class TrainedModel:
    target: str
    version: str
    algorithm: str
    features: list[str]
    estimator: Estimator
    calibrator: IsotonicMulticlass
    contract: dict
    train_start: date
    train_end: date
    data_hash: str
    feature_set_version: str
    is_synthetic_data: bool
    metrics: dict[str, Any] = field(default_factory=dict)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.calibrator.transform(self.estimator.predict_proba(X[self.features]))

    def proba_dict(self, row: pd.Series) -> dict[str, float]:
        p = self.predict(pd.DataFrame([row]))[0]
        return {
            "down": float(p[CLASSES.index(-1)]),
            "neutral": float(p[CLASSES.index(0)]),
            "up": float(p[CLASSES.index(1)]),
        }


def frame_hash(df: pd.DataFrame, cols: list[str]) -> str:
    h = hashlib.sha256(pd.util.hash_pandas_object(df[cols], index=False).to_numpy().tobytes())
    return h.hexdigest()


class ModelRegistry:
    def __init__(self, engine: Engine, data_dir: Path) -> None:
        self.engine, self.dir = engine, data_dir / "models"

    def register(self, m: TrainedModel, status: str = "candidate", gate_report: dict | None = None) -> int:
        path = self.dir / m.target / f"{m.version}.joblib"
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(m, path)
        with self.engine.begin() as conn:
            res = conn.execute(
                insert(s.model_registry).values(
                    target=m.target,
                    version=m.version,
                    algorithm=m.algorithm,
                    status=status,
                    created_at=utcnow(),
                    train_start=m.train_start,
                    train_end=m.train_end,
                    data_hash=m.data_hash,
                    feature_set_version=m.feature_set_version,
                    params={"features": m.features, "contract": m.contract},
                    metrics=_jsonable(m.metrics),
                    gate_report=_jsonable(gate_report or {}),
                    artifact_path=str(path),
                    is_synthetic_data=m.is_synthetic_data,
                )
            )
            return int(res.inserted_primary_key[0])  # type: ignore[index]

    def set_status(self, model_id: int, status: str, gate_report: dict | None = None) -> None:
        t = s.model_registry
        vals: dict[str, Any] = {"status": status}
        if gate_report is not None:
            vals["gate_report"] = _jsonable(gate_report)
        if status == "production":
            vals["promoted_at"] = utcnow()
        if status == "retired":
            vals["retired_at"] = utcnow()
        with self.engine.begin() as conn:
            conn.execute(t.update().where(t.c.id == model_id).values(**vals))

    def promote(self, model_id: int, gate_report: dict) -> None:
        """Make ``model_id`` production; the previous production model is retired (kept for rollback)."""
        row = self.get(model_id)
        assert row is not None
        cur = self.production_row(row["target"])
        if cur is not None:
            self.set_status(cur["id"], "retired")
        self.set_status(model_id, "production", gate_report)

    def rollback(self, target: str) -> int | None:
        """Restore the most recently retired model as production; demote the current one."""
        t = s.model_registry
        with self.engine.connect() as conn:
            prev = conn.execute(
                select(t)
                .where(and_(t.c.target == target, t.c.status == "retired"))
                .order_by(t.c.retired_at.desc(), t.c.id.desc())
            ).first()
        if prev is None:
            return None
        cur = self.production_row(target)
        if cur is not None:
            self.set_status(cur["id"], "rejected", {"reason": "rolled back"})
        self.set_status(prev.id, "production")
        return int(prev.id)

    def get(self, model_id: int) -> dict | None:
        with self.engine.connect() as conn:
            r = conn.execute(select(s.model_registry).where(s.model_registry.c.id == model_id)).first()
        return dict(r._mapping) if r else None

    def production_row(self, target: str) -> dict | None:
        t = s.model_registry
        with self.engine.connect() as conn:
            r = conn.execute(select(t).where(and_(t.c.target == target, t.c.status == "production"))).first()
        return dict(r._mapping) if r else None

    def load(self, model_id: int) -> TrainedModel:
        row = self.get(model_id)
        assert row is not None
        return joblib.load(row["artifact_path"])  # artefacts are written only by this registry

    def load_production(self, target: str) -> TrainedModel | None:
        row = self.production_row(target)
        return None if row is None else self.load(row["id"])

    def list(self, target: str | None = None) -> list[dict]:
        t = s.model_registry
        q = select(t).order_by(t.c.id.desc())
        if target:
            q = q.where(t.c.target == target)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_jsonable(v) for v in x]
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, float) and not np.isfinite(x):
        return None
    if isinstance(x, date):
        return x.isoformat()
    return x
