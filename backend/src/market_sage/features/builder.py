"""Point-in-time feature construction (feature set ``fs1``).

Features for session t use only bars with session_date <= t (all windows trailing). Daily bars for
session t are available after that session closes, so a forecast at cutoff t can use row t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from market_sage.analysis.regime import classify_regime
from market_sage.features import indicators as ind
from market_sage.features.patterns import candle_flags

FEATURE_SET_VERSION = "fs1"

MODEL_FEATURES = [
    "ret_1",
    "ret_5",
    "ret_20",
    "ret_60",
    "c_sma20",
    "c_sma50",
    "c_sma200",
    "sma20_sma50",
    "macd_hist_n",
    "rsi14",
    "stoch_k",
    "bb_pctb",
    "bb_width",
    "atr_pct",
    "adx14",
    "di_spread",
    "vol_ratio20",
    "vol_trend",
    "delivery_pct",
    "delivery_ratio",
    "rs_index20",
    "rs_sector20",
    "dist_52w_high",
    "dist_52w_low",
    "vol20",
    "vol_contraction",
    "slope20",
    "breakout20",
    "breakdown20",
    "gap_pct",
    "obv_slope20",
    "index_ret20",
    "index_vol20",
    "index_above_sma200",
    "bullish_engulfing",
    "bearish_engulfing",
    "hammer",
    "shooting_star",
]


def build_features(
    bars: pd.DataFrame, index_bars: pd.DataFrame | None = None, sector_bars: pd.DataFrame | None = None
) -> pd.DataFrame:
    """``bars``: adjusted daily bars for one instrument (sorted). Returns one row per session."""
    df = bars.sort_values("session_date").reset_index(drop=True)
    c, h, lo, v = (df[k].astype(float) for k in ("close", "high", "low", "volume"))
    f = pd.DataFrame(
        {
            "session_date": df["session_date"],
            "close": c,
            "high": h,
            "low": lo,
            "open": df["open"].astype(float),
            "volume": v,
        }
    )
    for n in (1, 5, 20, 60):
        f[f"ret_{n}"] = c.pct_change(n)
    s20, s50, s200 = ind.sma(c, 20), ind.sma(c, 50), ind.sma(c, 200)
    f["c_sma20"], f["c_sma50"], f["c_sma200"] = c / s20 - 1, c / s50 - 1, c / s200 - 1
    f["sma20_sma50"] = s20 / s50 - 1
    _, _, hist = ind.macd(c)
    f["macd_hist_n"] = hist / c
    f["rsi14"] = ind.rsi(c, 14)
    f["stoch_k"], _ = ind.stochastic(h, lo, c)
    bl, bm, bu = ind.bollinger(c)
    f["bb_pctb"] = (c - bl) / (bu - bl).replace(0, np.nan)
    f["bb_width"] = (bu - bl) / bm
    atr = ind.atr(h, lo, c, 14)
    f["atr14"] = atr
    f["atr_pct"] = atr / c
    adx, pdi, mdi = ind.adx(h, lo, c, 14)
    f["adx14"], f["di_spread"] = adx, pdi - mdi
    vavg = v.rolling(20, min_periods=20).mean()
    f["vol_ratio20"] = v / vavg.replace(0, np.nan)
    f["vol_trend"] = v.rolling(5, min_periods=5).mean() / vavg.replace(0, np.nan)
    dq = df["delivery_qty"].astype(float) if "delivery_qty" in df else pd.Series(np.nan, index=df.index)
    dp = dq / v.replace(0, np.nan)
    f["delivery_pct"] = dp
    f["delivery_ratio"] = dp / dp.rolling(20, min_periods=10).mean()
    f["dist_52w_high"] = c / h.rolling(250, min_periods=120).max() - 1
    f["dist_52w_low"] = c / lo.rolling(250, min_periods=120).min() - 1
    r = c.pct_change()
    f["vol20"] = r.rolling(20, min_periods=20).std() * np.sqrt(252)
    f["vol_contraction"] = f["vol20"] / (r.rolling(60, min_periods=60).std() * np.sqrt(252))
    f["slope20"] = ind.rolling_slope(np.log(c), 20) * 20
    f["breakout20"] = (c > h.shift(1).rolling(20, min_periods=20).max()).astype(float)
    f["breakdown20"] = (c < lo.shift(1).rolling(20, min_periods=20).min()).astype(float)
    f["gap_pct"] = df["open"].astype(float) / c.shift(1) - 1
    obv = ind.obv(c, v)
    f["obv_slope20"] = ind.rolling_slope(obv, 20) / vavg.replace(0, np.nan)
    f = pd.concat([f, candle_flags(df)], axis=1)
    f["rs_index20"] = np.nan
    f["rs_sector20"] = np.nan
    if index_bars is not None and not index_bars.empty:
        reg = classify_regime(index_bars.sort_values("session_date"))
        ic = index_bars.sort_values("session_date")[["session_date", "close"]].rename(columns={"close": "_ic"})
        f = f.merge(reg, on="session_date", how="left").merge(ic, on="session_date", how="left")
        f["rs_index20"] = f["ret_20"] - f["_ic"].pct_change(20)
        f = f.drop(columns="_ic")
    else:
        for col in ("index_ret20", "index_vol20", "index_above_sma200", "regime_confidence"):
            f[col] = np.nan
        f["regime_trend"], f["regime_vol"], f["regime_transition"] = "unknown", "unknown", False
    if sector_bars is not None and not sector_bars.empty:
        sc = sector_bars.sort_values("session_date")[["session_date", "close"]].rename(columns={"close": "_sc"})
        f = f.merge(sc, on="session_date", how="left")
        f["rs_sector20"] = f["ret_20"] - f["_sc"].pct_change(20)
        f = f.drop(columns="_sc")
    return f.reset_index(drop=True)
