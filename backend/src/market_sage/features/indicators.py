"""Technical indicators, implemented in-house with causal (trailing-only) windows.

Every function uses only data at or before each row, so values at session t never depend on t+1..
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).mean()


def ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False, min_periods=n).mean()


def wilder(x: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing seeded with the simple mean of the first n valid values (classic definition)."""
    vals = x.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    valid = np.flatnonzero(~np.isnan(vals))
    if len(valid) < n:
        return pd.Series(out, index=x.index)
    start = valid[0]
    seed_end = start + n - 1
    if np.isnan(vals[start : seed_end + 1]).any():
        return x.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    out[seed_end] = vals[start : seed_end + 1].mean()
    for i in range(seed_end + 1, len(vals)):
        v = vals[i]
        out[i] = out[i - 1] if np.isnan(v) else out[i - 1] + (v - out[i - 1]) / n
    return pd.Series(out, index=x.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up, down = wilder(d.clip(lower=0), n), wilder(-d.clip(upper=0), n)
    rs = up / down.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(down != 0, 100.0).where(up.notna())


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14, d: int = 3
) -> tuple[pd.Series, pd.Series]:
    hh, ll = high.rolling(n, min_periods=n).max(), low.rolling(n, min_periods=n).min()
    k = 100 * (close - ll) / (hh - ll).replace(0, np.nan)
    return k, k.rolling(d, min_periods=d).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return mid - k * sd, mid, mid + k * sd


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    return pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return wilder(true_range(high, low, close), n)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up, down = high.diff(), -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    tr = wilder(true_range(high, low, close), n)
    plus_di = 100 * wilder(plus_dm, n) / tr
    minus_di = 100 * wilder(minus_dm, n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return wilder(dx, n), plus_di, minus_di


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, session: pd.Series) -> pd.Series:
    """Intraday VWAP, reset each session (meaningful on intraday bars only)."""
    tp = (high + low + close) / 3
    pv = (tp * volume).groupby(session).cumsum()
    return pv / volume.groupby(session).cumsum().replace(0, np.nan)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    return (np.sign(close.diff()).fillna(0) * volume).cumsum()


def rolling_slope(y: pd.Series, n: int) -> pd.Series:
    """OLS slope of y over trailing n points (per step)."""
    x = np.arange(n, dtype=float)
    xm = x - x.mean()
    denom = (xm**2).sum()
    return y.rolling(n, min_periods=n).apply(lambda w: float(np.dot(xm, w - w.mean()) / denom), raw=True)
