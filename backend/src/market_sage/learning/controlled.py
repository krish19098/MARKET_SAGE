"""Controlled learning: candidate models are trained separately, judged on chronologically unseen data
against predefined gates, and promoted only if every gate passes. Production is never retrained in place;
the previous model is retained for rollback. No per-trade retraining.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, select

from market_sage.db import schema as s
from market_sage.features.builder import MODEL_FEATURES
from market_sage.features.store import FeatureStore
from market_sage.models.calibration import CLASSES, brier_multiclass, reliability
from market_sage.models.estimators import make_estimator
from market_sage.models.registry import ModelRegistry, TrainedModel
from market_sage.models.targets import ForecastContract
from market_sage.models.train import build_dataset, train_candidate
from market_sage.models.walkforward import economic_utility

TARGET = "tb5_atr"


class InsufficientHistory(ValueError):
    """Not enough labelled sessions for walk-forward folds plus the holdout; a normal skip, not a failure."""


@dataclass(frozen=True)
class GateCriteria:
    """Defined before evaluation and stored with every gate report."""

    min_brier_skill_vs_climatology: float = 0.002
    max_oos_ece: float = 0.05
    min_oos_trades: int = 30
    min_oos_mean_net: float = 0.0
    min_positive_skill_fold_share: float = 0.6
    holdout_sessions: int = 60
    holdout_must_beat_climatology: bool = True
    holdout_tolerance_vs_production: float = 0.002


@dataclass
class CycleResult:
    candidate_id: int
    promoted: bool
    gate_report: dict[str, Any]
    candidate: TrainedModel


def _holdout_eval(model: TrainedModel, hold: pd.DataFrame, clim_p: np.ndarray, cost: float) -> dict[str, Any]:
    y = hold["label"].to_numpy()
    p = model.predict(hold)
    clim = np.tile(clim_p, (len(hold), 1))
    return {"n": int(len(hold)), "brier": brier_multiclass(p, y), "brier_climatology": brier_multiclass(clim, y),
            "ece_up": reliability(p[:, CLASSES.index(1)], (y == 1).astype(float))["ece"],
            "utility": economic_utility(p[:, CLASSES.index(1)], hold["label_ret"].to_numpy(), cost, 0.45)}


def run_learning_cycle(store: FeatureStore, registry: ModelRegistry, cutoff: date, *, is_synthetic: bool,
                       criteria: GateCriteria | None = None, contract: ForecastContract | None = None,
                       n_folds: int = 4, universe_size: int = 200) -> CycleResult:
    criteria = criteria or GateCriteria()
    contract = contract or ForecastContract()
    # Universe chosen with information available at the cycle cutoff (liquidity ranking, point-in-time).
    full = build_dataset(store, cutoff, contract, store.mds.liquid_universe(cutoff, universe_size))
    sessions = np.array(sorted(full["session_date"].unique()))
    if len(sessions) <= criteria.holdout_sessions + 400:
        raise InsufficientHistory("insufficient history for a learning cycle")
    hold_start = sessions[-criteria.holdout_sessions]
    train_data = full[full["label_known"] < hold_start]  # candidate never sees holdout labels
    hold = full[full["session_date"] >= hold_start]
    cand, choice, _ = train_candidate(store, hold_start, contract, n_folds=n_folds, is_synthetic=is_synthetic,
                                      data=train_data)
    summ = cand.metrics["walk_forward"]["summary"]
    sel = choice.best
    clim_b = summ["climatology"]["brier_mean"]
    report: dict[str, Any] = {"criteria": asdict(criteria), "selected_algorithm": sel, "holdout_start": str(hold_start),
                              "train_end": str(cand.train_end), "checks": {}}
    chk = report["checks"]
    sel_b = summ[sel]["brier_mean"]
    chk["brier_skill_vs_climatology"] = {"value": 1 - sel_b / clim_b, "pass": sel != "climatology"
                                         and 1 - sel_b / clim_b >= criteria.min_brier_skill_vs_climatology}
    ece = cand.metrics["walk_forward"]["calibration"][sel]["ece"]
    chk["oos_calibration_ece"] = {"value": ece, "pass": ece <= criteria.max_oos_ece}
    util = summ[sel]["utility"]
    chk["oos_trades"] = {"value": util["trades"], "pass": util["trades"] >= criteria.min_oos_trades}
    chk["oos_mean_net"] = {"value": util["mean_net"], "pass": util["mean_net"] > criteria.min_oos_mean_net}
    clim_folds = summ["climatology"]["folds_brier"]
    pos = float(np.mean([b < c for b, c in zip(summ[sel]["folds_brier"], clim_folds, strict=True)])) if sel != "climatology" else 0.0
    chk["fold_stability"] = {"value": pos, "pass": pos >= criteria.min_positive_skill_fold_share}
    clim_p = np.array([(train_data["label"] == c).mean() for c in CLASSES])
    ho = _holdout_eval(cand, hold, clim_p, contract.round_trip_cost)
    report["holdout"] = ho
    chk["holdout_vs_climatology"] = {"value": ho["brier"] - ho["brier_climatology"],
                                     "pass": (not criteria.holdout_must_beat_climatology)
                                     or ho["brier"] < ho["brier_climatology"]}
    prod = registry.load_production(TARGET)
    if prod is not None and prod.train_end < hold_start:
        hp = _holdout_eval(prod, hold, clim_p, contract.round_trip_cost)
        report["holdout_production"] = hp
        chk["holdout_vs_production"] = {"value": ho["brier"] - hp["brier"],
                                        "pass": ho["brier"] <= hp["brier"] + criteria.holdout_tolerance_vs_production}
    elif prod is not None:
        report["holdout_production"] = "skipped: production model trained on data overlapping the holdout"
    passed = all(c["pass"] for c in chk.values())
    report["decision"] = "promoted" if passed else "rejected"
    report["failed_checks"] = [k for k, v in chk.items() if not v["pass"]]
    cid = registry.register(cand, status="candidate", gate_report=report)
    if passed:
        registry.promote(cid, report)
    else:
        registry.set_status(cid, "rejected", report)
    return CycleResult(cid, passed, report, cand)


def drift_check(engine: Engine, registry: ModelRegistry, tolerance: float = 0.10, min_n: int = 50) -> dict[str, Any]:
    """Compare production model's live (ledger-evaluated) Brier with its walk-forward expectation."""
    row = registry.production_row(TARGET)
    if row is None:
        return {"status": "no production model"}
    with engine.connect() as conn:
        rows = conn.execute(select(s.evaluations.c.metrics, s.predictions.c.model_version)
                            .join(s.predictions, s.predictions.c.id == s.evaluations.c.prediction_id)
                            .where(s.evaluations.c.horizon == "5s")).fetchall()
    b = [r.metrics["brier"] for r in rows if r.model_version == row["version"] and r.metrics.get("brier") is not None]
    sel = (row["metrics"] or {}).get("selected")
    expected = (row["metrics"] or {}).get("walk_forward", {}).get("summary", {}).get(sel, {}).get("brier_mean")
    if len(b) < min_n or expected is None:
        return {"status": "insufficient live sample", "n": len(b), "expected_brier": expected}
    live = float(np.mean(b))
    drift = live > expected * (1 + tolerance)
    return {"status": "drift" if drift else "ok", "n": len(b), "live_brier": live, "expected_brier": expected,
            "action": "schedule candidate training and review" if drift else "none"}


def snapshot_evaluation_dataset(engine: Engine, out_dir: Path) -> dict[str, Any]:
    """Versioned dataset of completed predictions + outcomes (for analysis/learning reports)."""
    with engine.connect() as conn:
        rows = conn.execute(select(s.predictions.c.id, s.predictions.c.created_at, s.predictions.c.symbol,
                                   s.predictions.c.action, s.predictions.c.model_version, s.evaluations.c.horizon,
                                   s.evaluations.c.metrics)
                            .join(s.evaluations, s.evaluations.c.prediction_id == s.predictions.c.id)).fetchall()
    df = pd.DataFrame([dict(r._mapping) for r in rows])
    if df.empty:
        return {"rows": 0}
    df["metrics"] = df["metrics"].astype(str)
    h = hashlib.sha256(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes()).hexdigest()[:16]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"evaluation_dataset_{h}.parquet"
    df.to_parquet(path, index=False)
    return {"rows": len(df), "version": h, "path": str(path)}


__all__ = ["GateCriteria", "drift_check", "make_estimator", "run_learning_cycle", "snapshot_evaluation_dataset",
           "MODEL_FEATURES"]
