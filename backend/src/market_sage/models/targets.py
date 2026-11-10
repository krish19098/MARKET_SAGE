"""Forecast contracts and target construction.

Target ``tb5_atr`` (triple barrier): decision at the post-close cutoff of session t; entry assumed at the
next session's open (executable convention); upper barrier entry + 1.5·ATR14, lower barrier entry − 1.0·ATR14;
horizon 5 sessions. Label = +1 if the upper barrier is touched first, −1 if the lower barrier is touched first
(both in the same bar → −1, conservative), 0 if neither (time-out). The label becomes known at session t+5.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ForecastContract:
    target: str = "tb5_atr"
    universe: str = "liquid NSE equities passing risk filters"
    prediction_time: str = "after 15:30 IST close of session t (EOD cutoff)"
    feature_cutoff: str = "daily bars with session_date <= t"
    price_convention: str = "entry at open of session t+1; barriers vs that entry"
    horizon_sessions: int = 5
    upper_atr: float = 1.5
    lower_atr: float = 1.0
    round_trip_cost: float = 0.0030  # assumption for research; real costs come from the cost model
    baseline: str = "climatology (training class frequencies) and momentum rule"
    validation: str = "expanding walk-forward, purged by label availability, embargo = horizon"
    calibration: str = "isotonic per class on the chronologically last 20% of each training window"
    no_forecast_when: str = "missing features, stale data, insufficient history (<220 sessions)"

    def to_dict(self) -> dict:
        return asdict(self)


def triple_barrier(f: pd.DataFrame, c: ForecastContract) -> pd.DataFrame:
    """Add ``label``, ``label_ret`` (gross return of the barrier outcome) and ``label_known``."""
    o, h, lo, cl, atr = (f[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close", "atr14"))
    n, H = len(f), c.horizon_sessions
    label = np.full(n, np.nan)
    lret = np.full(n, np.nan)
    for t in range(n - H):
        entry, a = o[t + 1], atr[t]
        if not (np.isfinite(entry) and np.isfinite(a) and a > 0):
            continue
        up, dn = entry + c.upper_atr * a, entry - c.lower_atr * a
        lab, r = 0.0, cl[t + H] / entry - 1
        for k in range(t + 1, t + H + 1):
            hit_dn, hit_up = lo[k] <= dn, h[k] >= up
            if hit_dn:  # conservative: if both in one bar, assume the stop first
                lab, r = -1.0, min(dn, o[k]) / entry - 1 if k > t + 1 else dn / entry - 1
                break
            if hit_up:
                lab, r = 1.0, max(up, o[k]) / entry - 1 if k > t + 1 else up / entry - 1
                break
        label[t], lret[t] = lab, r
    out = f.copy()
    out["label"] = label
    out["label_ret"] = lret
    out["label_known"] = f["session_date"].shift(-H)
    return out
