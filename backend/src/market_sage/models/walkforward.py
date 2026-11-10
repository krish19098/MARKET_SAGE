"""Chronological walk-forward validation with purging (label availability) and embargo.

No random splits: each fold trains only on rows whose labels were *known* before the fold's test start,
calibrates on the chronologically last 20% of that training window, and is scored on later unseen data.
Economic utility uses barrier outcomes net of a round-trip cost assumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from market_sage.models.calibration import (
    CLASSES,
    IsotonicMulticlass,
    brier_multiclass,
    log_loss_multiclass,
    reliability,
)
from market_sage.models.estimators import make_estimator


@dataclass
class FoldResult:
    fold: int
    train_end: str
    test_start: str
    test_end: str
    n_train: int
    n_test: int
    metrics: dict[str, dict]


@dataclass
class WalkForwardReport:
    folds: list[FoldResult]
    summary: dict[str, dict]
    calibration: dict[str, dict]
    oos_predictions: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)

    def to_dict(self) -> dict:
        return {"folds": [f.__dict__ for f in self.folds], "summary": self.summary, "calibration": self.calibration}


def economic_utility(p_up: np.ndarray, label_ret: np.ndarray, cost: float, threshold: float) -> dict:
    """Trade when calibrated P(up-barrier first) >= threshold; return stats of net barrier outcomes."""
    take = p_up >= threshold
    net = label_ret[take] - cost
    if take.sum() == 0:
        return {"trades": 0, "mean_net": 0.0, "win_rate": None, "profit_factor": None, "total_net": 0.0}
    gains, losses = net[net > 0].sum(), -net[net < 0].sum()
    return {
        "trades": int(take.sum()),
        "mean_net": float(net.mean()),
        "win_rate": float((net > 0).mean()),
        "profit_factor": float(gains / losses) if losses > 0 else None,
        "total_net": float(net.sum()),
        "max_drawdown": float(_max_dd(net)),
    }


def _max_dd(net: np.ndarray) -> float:
    eq = np.cumsum(net)
    return float((np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq).max()) if len(eq) else 0.0


def run_walk_forward(
    data: pd.DataFrame,
    features: list[str],
    models: tuple[str, ...],
    *,
    n_folds: int = 4,
    min_train_sessions: int = 300,
    horizon: int = 5,
    cost: float = 0.003,
    threshold: float = 0.45,
    seed: int = 0,
) -> WalkForwardReport:
    """``data``: rows with features, label, label_ret, label_known, session_date (pooled universe)."""
    d = data[np.isfinite(data["label"])].sort_values("session_date").reset_index(drop=True)
    sessions = np.array(sorted(d["session_date"].unique()))
    if len(sessions) < min_train_sessions + n_folds * 20:
        raise ValueError("insufficient history for walk-forward validation")
    test_sessions = sessions[min_train_sessions:]
    bounds = np.array_split(test_sessions, n_folds)
    folds, oos = [], []
    for k, block in enumerate(bounds):
        t0, t1 = block[0], block[-1]
        train = d[d["label_known"] < t0]  # purge: only labels observable before test start
        emb_idx = max(0, np.searchsorted(sessions, t0) - horizon)
        train = train[train["session_date"] < sessions[emb_idx]]  # embargo
        test = d[(d["session_date"] >= t0) & (d["session_date"] <= t1)]
        cut = int(len(train) * 0.8)
        fit_part, cal_part = train.iloc[:cut], train.iloc[cut:]
        fm: dict[str, dict] = {}
        y_test = test["label"].to_numpy()
        preds = {
            "session_date": test["session_date"].to_numpy(),
            "instrument_id": test["instrument_id"].to_numpy(),
            "label": y_test,
            "label_ret": test["label_ret"].to_numpy(),
        }
        for name in models:
            est = make_estimator(name, seed).fit(fit_part[features], fit_part["label"].to_numpy())
            cal = IsotonicMulticlass().fit(est.predict_proba(cal_part[features]), cal_part["label"].to_numpy())
            p = cal.transform(est.predict_proba(test[features]))
            preds[f"p_up_{name}"] = p[:, CLASSES.index(1)]
            fm[name] = {
                "brier": brier_multiclass(p, y_test),
                "log_loss": log_loss_multiclass(p, y_test),
                "accuracy": float((np.array(CLASSES)[p.argmax(1)] == y_test).mean()),
                "utility": economic_utility(p[:, CLASSES.index(1)], test["label_ret"].to_numpy(), cost, threshold),
            }
        folds.append(FoldResult(k, str(train["session_date"].max()), str(t0), str(t1), len(train), len(test), fm))
        oos.append(pd.DataFrame(preds))
    oos_df = pd.concat(oos, ignore_index=True)
    summary, calib = {}, {}
    for name in models:
        b = [f.metrics[name]["brier"] for f in folds]
        ll = [f.metrics[name]["log_loss"] for f in folds]
        util = economic_utility(oos_df[f"p_up_{name}"].to_numpy(), oos_df["label_ret"].to_numpy(), cost, threshold)
        summary[name] = {
            "brier_mean": float(np.mean(b)),
            "brier_std": float(np.std(b)),
            "log_loss_mean": float(np.mean(ll)),
            "folds_brier": b,
            "utility": util,
            "n_oos": int(len(oos_df)),
        }
        calib[name] = reliability(oos_df[f"p_up_{name}"].to_numpy(), (oos_df["label"] == 1).to_numpy().astype(float))
    return WalkForwardReport(folds, summary, calib, oos_df)


def fold_dates(report: WalkForwardReport) -> list[tuple[date, date]]:
    return [(date.fromisoformat(f.test_start), date.fromisoformat(f.test_end)) for f in report.folds]
