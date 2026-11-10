"""Early opportunity / risk setup detection with explicit lifecycle stages.

Stages: ``early`` (developing condition, trigger not confirmed) → ``developing`` → ``confirmed``
(pre-defined trigger occurred) → ``invalidated``. Early stages are probabilistic warnings, never
presented as confirmed events. Each setup carries its trigger and invalidation levels so later
evaluation can measure lead time and false-alert rate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Setup:
    name: str
    direction: str  # bullish | bearish | neutral
    stage: str  # early | developing | confirmed | invalidated
    trigger: float | None
    invalidation: float | None
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def detect_setups(f: pd.DataFrame) -> list[Setup]:
    """Detect setups on the last row of a feature frame (requires ~60 rows)."""
    if len(f) < 60:
        return []
    r, prev = f.iloc[-1], f.iloc[-2]
    c, a = float(r["close"]), float(r["atr14"])
    if not np.isfinite(a) or a <= 0:
        return []
    out: list[Setup] = []
    hi20 = float(f["high"].iloc[-21:-1].max())
    lo20 = float(f["low"].iloc[-21:-1].min())
    vr = float(r.get("vol_ratio20", np.nan))
    vc = float(r.get("vol_contraction", np.nan))

    # Breakout lifecycle. Invalidation is measured against the level that was actually broken
    # (the prior 20-session high at the breakout bar), not the new high created by the breakout.
    prior_hi = f["high"].shift(1).rolling(20).max()
    broke = (f["close"] > prior_hi).iloc[-4:-1]
    broken_level = float(prior_hi.iloc[-4:-1][broke].iloc[-1]) if broke.any() else None
    if c > hi20:
        stage = "confirmed" if vr >= 1.5 else "developing"
        out.append(Setup("breakout", "bullish", stage, hi20, hi20 - a,
                         f"close {c:.2f} above 20-session high {hi20:.2f}, volume {vr:.1f}x"))
    elif broken_level is not None and c < broken_level - 0.25 * a:
        out.append(Setup("breakout", "bullish", "invalidated", broken_level, None,
                         f"failed breakout: closed back below broken level {broken_level:.2f}"))
    elif hi20 - c <= 0.5 * a:
        extra = " with volatility contraction" if np.isfinite(vc) and vc < 0.8 else ""
        out.append(Setup("breakout", "bullish", "early", hi20, c - 1.5 * a,
                         f"price within 0.5 ATR of 20-session high {hi20:.2f}{extra}"))

    # Breakdown lifecycle (risk for holders)
    if c < lo20:
        stage = "confirmed" if vr >= 1.5 else "developing"
        out.append(
            Setup(
                "breakdown",
                "bearish",
                stage,
                lo20,
                lo20 + a,
                f"close {c:.2f} below 20-session low {lo20:.2f}, volume {vr:.1f}x",
            )
        )
    elif c - lo20 <= 0.5 * a:
        out.append(
            Setup(
                "breakdown", "bearish", "early", lo20, c + 1.5 * a, f"price within 0.5 ATR of 20-session low {lo20:.2f}"
            )
        )

    # Relative-strength improvement
    rs = f["rs_index20"].iloc[-6:]
    if rs.notna().all() and rs.iloc[0] < 0 < rs.iloc[-1]:
        stage = "developing" if rs.iloc[-1] > 0.03 else "early"
        out.append(
            Setup(
                "relative_strength_improvement",
                "bullish",
                stage,
                None,
                None,
                f"20-session RS vs index turned positive ({rs.iloc[-1]:+.1%})",
            )
        )

    # Volatility contraction (direction undetermined)
    if np.isfinite(vc) and vc < 0.6:
        out.append(
            Setup(
                "volatility_contraction",
                "neutral",
                "early",
                hi20,
                lo20,
                f"20d/60d volatility ratio {vc:.2f}; expansion direction unknown",
            )
        )

    # Momentum shift (MACD histogram sign change)
    if np.isfinite(r["macd_hist_n"]) and np.isfinite(prev["macd_hist_n"]):
        if prev["macd_hist_n"] <= 0 < r["macd_hist_n"]:
            out.append(Setup("momentum_shift", "bullish", "early", None, None, "MACD histogram turned positive"))
        elif prev["macd_hist_n"] >= 0 > r["macd_hist_n"]:
            out.append(Setup("momentum_shift", "bearish", "early", None, None, "MACD histogram turned negative"))

    # Volume anomaly
    if np.isfinite(vr) and vr >= 2.5:
        out.append(
            Setup(
                "volume_anomaly",
                "bullish" if r["ret_1"] > 0 else "bearish",
                "early",
                None,
                None,
                f"volume {vr:.1f}x 20-day average (observation; cause unknown)",
            )
        )

    # Support-zone reversal
    near_low = float(f["low"].iloc[-60:-5].min())
    if abs(float(r["low"]) - near_low) <= 0.75 * a and (r.get("hammer", 0) == 1 or r.get("bullish_engulfing", 0) == 1):
        stage = "confirmed" if c > float(prev["high"]) else "early"
        out.append(
            Setup(
                "support_reversal",
                "bullish",
                stage,
                float(prev["high"]),
                near_low - 0.5 * a,
                f"reversal candle near 60-session support {near_low:.2f}",
            )
        )
    return out
