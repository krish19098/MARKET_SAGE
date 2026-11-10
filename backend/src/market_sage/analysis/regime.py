"""Market regime classification from index bars (heuristic, causal, with confidence).

Labels: bull | bear | sideways, crossed with high_vol | low_vol, plus a ``transition`` flag when the
trend label changed within the last 5 sessions. Thresholds are parameters to be validated; the regime
label is evidence with uncertainty, not a fact.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_sage.features.indicators import rolling_slope, sma


def classify_regime(index_bars: pd.DataFrame) -> pd.DataFrame:
    c = index_bars["close"].astype(float).reset_index(drop=True)
    s50, s200 = sma(c, 50), sma(c, 200)
    slope50 = rolling_slope(np.log(c), 20)
    r = c.pct_change()
    vol20 = r.rolling(20, min_periods=20).std() * np.sqrt(252)
    vol_med = vol20.rolling(250, min_periods=60).median()
    trend_score = (np.sign(c - s200).fillna(0) + np.sign(c - s50).fillna(0) + np.sign(slope50).fillna(0)) / 3.0
    trend = np.where(trend_score >= 0.66, "bull", np.where(trend_score <= -0.66, "bear", "sideways"))
    trend = pd.Series(trend, index=c.index).where(s200.notna(), "unknown")
    vol_state = np.where(vol20 > vol_med * 1.2, "high_vol", "low_vol")
    vol_state = pd.Series(vol_state, index=c.index).where(vol_med.notna(), "unknown")
    changed = trend.ne(trend.shift(1)).astype(int).rolling(5, min_periods=1).sum() > 0
    changed.iloc[0] = False
    out = pd.DataFrame(
        {
            "session_date": index_bars["session_date"].to_numpy(),
            "regime_trend": trend.to_numpy(),
            "regime_vol": vol_state.to_numpy(),
            "regime_transition": changed.to_numpy(),
            "regime_confidence": trend_score.abs().to_numpy(),
            "index_ret20": c.pct_change(20).to_numpy(),
            "index_vol20": vol20.to_numpy(),
            "index_above_sma200": (c > s200).astype(float).where(s200.notna()).to_numpy(),
        }
    )
    return out
