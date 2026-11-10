"""Dataset assembly, model-ladder evaluation and final training (all point-in-time at a cutoff)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from market_sage.features.builder import FEATURE_SET_VERSION, MODEL_FEATURES
from market_sage.features.store import FeatureStore
from market_sage.models.calibration import IsotonicMulticlass
from market_sage.models.estimators import LADDER, make_estimator
from market_sage.models.registry import TrainedModel, frame_hash
from market_sage.models.targets import ForecastContract, triple_barrier
from market_sage.models.walkforward import WalkForwardReport, run_walk_forward

MIN_HISTORY = 220


def build_dataset(
    store: FeatureStore, cutoff: date, contract: ForecastContract, instrument_ids: list[int] | None = None
) -> pd.DataFrame:
    """Labelled rows whose labels were already observable at ``cutoff`` (no future information)."""
    frames = []
    ids = instrument_ids or [i["id"] for i in store.mds.instruments.all(include_indices=False)]
    for iid in ids:
        f = store.instrument_features(iid, until=cutoff)
        if len(f) < MIN_HISTORY:
            continue
        f = triple_barrier(f.iloc[MIN_HISTORY // 2 :].reset_index(drop=True), contract)
        frames.append(f[f["label_known"].notna() & (f["label_known"] <= cutoff)])
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(["session_date", "instrument_id"]).reset_index(drop=True)


@dataclass
class LadderResult:
    report: WalkForwardReport
    best: str
    reason: str


def select_model(report: WalkForwardReport) -> LadderResult:
    """Pick the learner with the best mean OOS Brier among those beating climatology; else climatology."""
    s = report.summary
    clim = s["climatology"]["brier_mean"]
    learners = [m for m in s if m not in ("climatology",)]
    better = [m for m in learners if s[m]["brier_mean"] < clim]
    if not better:
        return LadderResult(report, "climatology", "no learner beat climatology out-of-sample")
    best = min(better, key=lambda m: s[m]["brier_mean"])
    return LadderResult(
        report, best, f"{best} has lowest OOS Brier ({s[best]['brier_mean']:.4f} vs climatology {clim:.4f})"
    )


def fit_final(
    data: pd.DataFrame,
    algorithm: str,
    contract: ForecastContract,
    cutoff: date,
    is_synthetic: bool,
    metrics: dict,
    seed: int = 0,
) -> TrainedModel:
    d = data.sort_values("session_date").reset_index(drop=True)
    cut = int(len(d) * 0.8)
    est = make_estimator(algorithm, seed).fit(d.iloc[:cut][MODEL_FEATURES], d.iloc[:cut]["label"].to_numpy())
    cal = IsotonicMulticlass().fit(est.predict_proba(d.iloc[cut:][MODEL_FEATURES]), d.iloc[cut:]["label"].to_numpy())
    version = f"{contract.target}-{algorithm}-{cutoff:%Y%m%d}"
    return TrainedModel(
        contract.target,
        version,
        algorithm,
        list(MODEL_FEATURES),
        est,
        cal,
        contract.to_dict(),
        d["session_date"].min(),
        d["session_date"].max(),
        frame_hash(d, ["instrument_id", "label"] + MODEL_FEATURES[:5]),
        FEATURE_SET_VERSION,
        is_synthetic,
        metrics,
    )


def train_candidate(
    store: FeatureStore,
    cutoff: date,
    contract: ForecastContract | None = None,
    models: tuple[str, ...] = LADDER,
    n_folds: int = 4,
    is_synthetic: bool = False,
    data: pd.DataFrame | None = None,
) -> tuple[TrainedModel, LadderResult, pd.DataFrame]:
    contract = contract or ForecastContract()
    data = data if data is not None else build_dataset(store, cutoff, contract)
    if data.empty:
        raise ValueError("no labelled data available at cutoff")
    rep = run_walk_forward(
        data, MODEL_FEATURES, models, n_folds=n_folds, horizon=contract.horizon_sessions, cost=contract.round_trip_cost
    )
    choice = select_model(rep)
    metrics = {
        "walk_forward": rep.to_dict(),
        "selected": choice.best,
        "selection_reason": choice.reason,
        "n_rows": int(len(data)),
        "label_distribution": {str(k): float(v) for k, v in data["label"].value_counts(normalize=True).items()},
    }
    model = fit_final(data, choice.best, contract, cutoff, is_synthetic, metrics)
    return model, choice, data


def oos_calibration_ok(metrics: dict, max_ece: float = 0.05) -> bool:
    sel = metrics.get("selected")
    cal = metrics.get("walk_forward", {}).get("calibration", {}).get(sel, {})
    return bool(cal) and cal.get("ece", 1.0) <= max_ece and cal.get("n", 0) >= 500


def summarize(rep: WalkForwardReport) -> pd.DataFrame:
    rows = []
    for m, v in rep.summary.items():
        u = v["utility"]
        rows.append(
            {
                "model": m,
                "brier": v["brier_mean"],
                "log_loss": v["log_loss_mean"],
                "trades": u["trades"],
                "mean_net": u["mean_net"],
                "profit_factor": u.get("profit_factor"),
                "ece": rep.calibration[m]["ece"],
            }
        )
    return pd.DataFrame(rows).sort_values("brier").reset_index(drop=True).replace({np.nan: None})
