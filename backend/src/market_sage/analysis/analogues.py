"""Historical market memory: point-in-time nearest-neighbour analogues.

Only rows whose forward outcome was already observable at the query cutoff are eligible, and the
standardisation statistics are computed from that eligible pool only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from market_sage.features.store import HORIZONS

ANALOGUE_FEATURES = [
    "ret_5",
    "ret_20",
    "c_sma50",
    "rsi14",
    "atr_pct",
    "vol_ratio20",
    "rs_index20",
    "vol_contraction",
    "slope20",
    "index_ret20",
    "bb_pctb",
    "dist_52w_high",
]


@dataclass
class AnalogueResult:
    sample_size: int
    method: str
    period: tuple[str, str] | None
    by_horizon: dict[int, dict[str, float]]
    regime_matched: bool

    def to_dict(self) -> dict:
        return {
            "sample_size": self.sample_size,
            "method": self.method,
            "period": self.period,
            "by_horizon": {str(k): v for k, v in self.by_horizon.items()},
            "regime_matched": self.regime_matched,
        }


def find_analogues(
    pool: pd.DataFrame,
    query: pd.Series,
    cutoff: date,
    k: int = 60,
    max_horizon: int = 20,
    exclude_instrument: int | None = None,
    regime: str | None = None,
) -> AnalogueResult | None:
    cols = [
        "instrument_id",
        "session_date",
        "regime_trend",
        *ANALOGUE_FEATURES,
        *[c for h in HORIZONS for c in (f"fwd_ret_{h}", f"mfe_{h}", f"mae_{h}")],
        f"known_{max_horizon}",
    ]
    pool = pool[[c for c in cols if c in pool.columns]]
    known = pool[f"known_{max_horizon}"]
    elig = pool[known.notna() & (known <= cutoff)]
    if exclude_instrument is not None:  # avoid near-duplicate overlapping windows of the same stock
        recent = pd.Timestamp(cutoff) - pd.Timedelta(days=90)
        elig = elig[~((elig["instrument_id"] == exclude_instrument) & (pd.to_datetime(elig["session_date"]) > recent))]
    regime_matched = False
    if regime and "regime_trend" in elig and (elig["regime_trend"] == regime).sum() >= 4 * k:
        elig = elig[elig["regime_trend"] == regime]
        regime_matched = True
    X = elig[ANALOGUE_FEATURES].astype(float)
    mask = np.isfinite(X).all(axis=1)
    X, elig = X[mask], elig[mask]
    q = query[ANALOGUE_FEATURES].astype(float)
    if len(X) < k or not np.isfinite(q).all():
        return None
    mu, sd = X.mean(), X.std(ddof=0).replace(0, 1.0)
    d = (((X - mu) / sd - (q - mu) / sd) ** 2).sum(axis=1) ** 0.5
    nn = elig.loc[d.nsmallest(k).index]
    out: dict[int, dict[str, float]] = {}
    for h in HORIZONS:
        r = nn[f"fwd_ret_{h}"].dropna()
        if r.empty:
            continue
        out[h] = {
            "mean": float(r.mean()),
            "median": float(r.median()),
            "p10": float(r.quantile(0.1)),
            "p90": float(r.quantile(0.9)),
            "win_rate": float((r > 0).mean()),
            "mfe_median": float(nn[f"mfe_{h}"].median()),
            "mae_median": float(nn[f"mae_{h}"].median()),
            "failure_rate": float((r < 0).mean()),
            "n": float(len(r)),
        }
    period = (str(nn["session_date"].min()), str(nn["session_date"].max()))
    return AnalogueResult(
        len(nn), f"kNN(k={k}) standardized euclidean on {len(ANALOGUE_FEATURES)} features", period, out, regime_matched
    )
