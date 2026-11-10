"""Candlestick and pivot-based chart patterns.

Pattern names alone are weak evidence: each detection reports context (trend, location, volume) and
confirmation state. Historical base rates are measured separately (``pattern_base_rates``) using only
past detections whose outcomes were already known.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from market_sage.features.structure import Pivot


def candle_flags(df: pd.DataFrame) -> pd.DataFrame:
    o, h, lo, c = df["open"], df["high"], df["low"], df["close"]
    body = (c - o).abs()
    rng = (h - lo).replace(0, np.nan)
    upper = h - pd.concat([o, c], axis=1).max(axis=1)
    lower = pd.concat([o, c], axis=1).min(axis=1) - lo
    po, pc = o.shift(1), c.shift(1)
    flags = pd.DataFrame(index=df.index)
    flags["doji"] = (body / rng < 0.1).astype(float)
    flags["marubozu"] = (body / rng > 0.9).astype(float)
    flags["hammer"] = ((lower > 2 * body) & (upper < body) & (body / rng < 0.4)).astype(float)
    flags["inverted_hammer"] = ((upper > 2 * body) & (lower < body) & (body / rng < 0.4) & (c > o)).astype(float)
    flags["shooting_star"] = ((upper > 2 * body) & (lower < body) & (body / rng < 0.4) & (c < o)).astype(float)
    flags["bullish_engulfing"] = ((pc < po) & (c > o) & (c >= po) & (o <= pc)).astype(float)
    flags["bearish_engulfing"] = ((pc > po) & (c < o) & (c <= po) & (o >= pc)).astype(float)
    o2, c2 = o.shift(2), c.shift(2)
    small_mid = (c.shift(1) - o.shift(1)).abs() < 0.3 * (c2 - o2).abs()
    flags["morning_star"] = ((c2 < o2) & small_mid & (c > o) & (c > (o2 + c2) / 2)).astype(float)
    flags["evening_star"] = ((c2 > o2) & small_mid & (c < o) & (c < (o2 + c2) / 2)).astype(float)
    return flags.fillna(0.0)


@dataclass(frozen=True)
class ChartPattern:
    name: str
    bias: str  # bullish | bearish
    confirmed: bool  # neckline/boundary broken on the latest bar
    level: float  # neckline / breakout level
    detail: str


def chart_patterns(known: list[Pivot], close: float, atr_value: float) -> list[ChartPattern]:
    """Detect patterns from the most recent confirmed pivots (tolerance in ATR units)."""
    out: list[ChartPattern] = []
    if not np.isfinite(atr_value) or atr_value <= 0:
        return out
    tol = 0.6 * atr_value
    seq = sorted(known, key=lambda p: p.idx)[-7:]
    highs = [p for p in seq if p.kind == "high"]
    lows = [p for p in seq if p.kind == "low"]
    if len(highs) >= 2 and lows:
        a, b = highs[-2], highs[-1]
        trough = [p for p in lows if a.idx < p.idx < b.idx]
        if abs(a.price - b.price) <= tol and trough:
            neck = min(p.price for p in trough)
            out.append(
                ChartPattern(
                    "double_top",
                    "bearish",
                    close < neck,
                    neck,
                    f"peaks {a.price:.2f}/{b.price:.2f}, neckline {neck:.2f}",
                )
            )
    if len(lows) >= 2 and highs:
        a, b = lows[-2], lows[-1]
        peak = [p for p in highs if a.idx < p.idx < b.idx]
        if abs(a.price - b.price) <= tol and peak:
            neck = max(p.price for p in peak)
            out.append(
                ChartPattern(
                    "double_bottom",
                    "bullish",
                    close > neck,
                    neck,
                    f"troughs {a.price:.2f}/{b.price:.2f}, neckline {neck:.2f}",
                )
            )
    if len(highs) >= 3 and len(lows) >= 2:
        ls, hd, rs = highs[-3:]
        if hd.price > ls.price + tol and hd.price > rs.price + tol and abs(ls.price - rs.price) <= 1.5 * tol:
            neck_pts = [p.price for p in lows if ls.idx < p.idx < rs.idx]
            if neck_pts:
                neck = min(neck_pts)
                out.append(
                    ChartPattern(
                        "head_and_shoulders",
                        "bearish",
                        close < neck,
                        neck,
                        f"head {hd.price:.2f}, shoulders {ls.price:.2f}/{rs.price:.2f}",
                    )
                )
    if len(lows) >= 3 and len(highs) >= 2:
        ls, hd, rs = lows[-3:]
        if hd.price < ls.price - tol and hd.price < rs.price - tol and abs(ls.price - rs.price) <= 1.5 * tol:
            neck_pts = [p.price for p in highs if ls.idx < p.idx < rs.idx]
            if neck_pts:
                neck = max(neck_pts)
                out.append(
                    ChartPattern(
                        "inverse_head_and_shoulders",
                        "bullish",
                        close > neck,
                        neck,
                        f"head {hd.price:.2f}, shoulders {ls.price:.2f}/{rs.price:.2f}",
                    )
                )
    if len(highs) >= 2 and len(lows) >= 2:
        h1, h2 = highs[-2], highs[-1]
        l1, l2 = lows[-2], lows[-1]
        falling_highs, rising_lows = h2.price < h1.price - tol / 2, l2.price > l1.price + tol / 2
        flat_highs, flat_lows = abs(h2.price - h1.price) <= tol / 2, abs(l2.price - l1.price) <= tol / 2
        if flat_highs and rising_lows:
            out.append(
                ChartPattern(
                    "ascending_triangle",
                    "bullish",
                    close > max(h1.price, h2.price),
                    max(h1.price, h2.price),
                    "flat resistance, rising lows",
                )
            )
        elif falling_highs and flat_lows:
            out.append(
                ChartPattern(
                    "descending_triangle",
                    "bearish",
                    close < min(l1.price, l2.price),
                    min(l1.price, l2.price),
                    "falling highs, flat support",
                )
            )
        elif falling_highs and rising_lows:
            out.append(
                ChartPattern(
                    "symmetrical_triangle",
                    "neutral",
                    close > h2.price or close < l2.price,
                    h2.price,
                    "converging highs and lows",
                )
            )
    return out


def flag_or_consolidation(df: pd.DataFrame, atr_series: pd.Series) -> ChartPattern | None:
    """Sharp move (pole) followed by a tight range (flag/pennant-like consolidation)."""
    if len(df) < 30:
        return None
    a = float(atr_series.iloc[-1])
    pole = df["close"].iloc[-15] / df["close"].iloc[-25] - 1
    rng = df["high"].iloc[-10:].max() - df["low"].iloc[-10:].min()
    if not np.isfinite(a) or a <= 0 or rng > 3.5 * a:
        return None
    top = float(df["high"].iloc[-11:-1].max())
    bottom = float(df["low"].iloc[-11:-1].min())
    close = float(df["close"].iloc[-1])
    if pole > 0.08:
        return ChartPattern("bull_flag", "bullish", close > top, top, f"pole {pole:+.1%}, tight range")
    if pole < -0.08:
        return ChartPattern("bear_flag", "bearish", close < bottom, bottom, f"pole {pole:+.1%}, tight range")
    return ChartPattern("consolidation", "neutral", close > top or close < bottom, top, "tight 10-session range")
