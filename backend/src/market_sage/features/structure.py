"""Price structure: confirmed swing pivots, trend classification, support/resistance zones.

A pivot at bar i is only *confirmed* k bars later, so it is attached to bar i+k (no look-ahead).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Pivot:
    idx: int  # bar index of the pivot itself
    confirmed_at: int  # first bar index at which it is known
    price: float
    kind: str  # high | low


def confirmed_pivots(high: np.ndarray, low: np.ndarray, k: int = 3) -> list[Pivot]:
    out: list[Pivot] = []
    n = len(high)
    for i in range(k, n - k):
        win_h, win_l = high[i - k : i + k + 1], low[i - k : i + k + 1]
        if high[i] == win_h.max() and (win_h == high[i]).sum() == 1:
            out.append(Pivot(i, i + k, float(high[i]), "high"))
        if low[i] == win_l.min() and (win_l == low[i]).sum() == 1:
            out.append(Pivot(i, i + k, float(low[i]), "low"))
    return out


def pivots_known_at(pivots: list[Pivot], t: int) -> list[Pivot]:
    return [p for p in pivots if p.confirmed_at <= t]


def trend_from_pivots(known: list[Pivot]) -> str:
    highs = [p for p in known if p.kind == "high"][-2:]
    lows = [p for p in known if p.kind == "low"][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return "undetermined"
    hh, hl = highs[1].price > highs[0].price, lows[1].price > lows[0].price
    if hh and hl:
        return "uptrend"
    if not hh and not hl:
        return "downtrend"
    return "range"


@dataclass(frozen=True)
class Zone:
    low: float
    high: float
    touches: int
    kind: str  # support | resistance


def sr_zones(known: list[Pivot], price: float, atr_value: float, lookback_idx: int) -> list[Zone]:
    """Cluster recent pivot prices within 0.5 ATR into zones; classify relative to current price."""
    pts = sorted(p.price for p in known if p.idx >= lookback_idx)
    if not pts or not np.isfinite(atr_value) or atr_value <= 0:
        return []
    tol = 0.5 * atr_value
    clusters: list[list[float]] = [[pts[0]]]
    for v in pts[1:]:
        if v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    zones = []
    for c in clusters:
        lo, hi = min(c), max(c)
        mid = (lo + hi) / 2
        zones.append(Zone(lo, hi, len(c), "support" if mid < price else "resistance"))
    return zones


def nearest_levels(zones: list[Zone], price: float) -> tuple[Zone | None, Zone | None]:
    sup = [z for z in zones if z.kind == "support"]
    res = [z for z in zones if z.kind == "resistance"]
    s = max(sup, key=lambda z: z.high) if sup else None
    r = min(res, key=lambda z: z.low) if res else None
    return s, r


def structure_summary(df: pd.DataFrame, atr_series: pd.Series, k: int = 3, lookback: int = 120) -> dict:
    """Structure evidence for the last bar of ``df`` using only confirmed information."""
    t = len(df) - 1
    piv = pivots_known_at(confirmed_pivots(df["high"].to_numpy(), df["low"].to_numpy(), k), t)
    price, a = float(df["close"].iloc[-1]), float(atr_series.iloc[-1])
    zones = sr_zones(piv, price, a, max(0, t - lookback))
    sup, res = nearest_levels(zones, price)
    prior_high = float(df["high"].iloc[-21:-1].max()) if len(df) > 21 else float("nan")
    prior_low = float(df["low"].iloc[-21:-1].min()) if len(df) > 21 else float("nan")
    return {
        "trend": trend_from_pivots(piv),
        "support": None if sup is None else {"low": sup.low, "high": sup.high, "touches": sup.touches},
        "resistance": None if res is None else {"low": res.low, "high": res.high, "touches": res.touches},
        "breakout_20d": bool(price > prior_high),
        "breakdown_20d": bool(price < prior_low),
        "pivots_used": len(piv),
    }
