"""Position assessment and alert rules (state transitions with hysteresis; no alerts for noise).

States: normal → early_warning → approaching_stop | approaching_target → stop_triggered | target1_hit
→ target2_hit. Only *transitions* (or new levels) produce alerts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from market_sage.models.setups import detect_setups

STATE_RANK = {"normal": 0, "early_warning": 1, "approaching_target": 1, "approaching_stop": 2, "target1_hit": 2,
              "target2_hit": 3, "stop_triggered": 4}


@dataclass
class Assessment:
    action: str                 # HOLD | EXIT | PARTIAL_EXIT
    state: str
    reasons: list[str]
    alerts: list[dict[str, Any]] = field(default_factory=list)
    thesis_valid: bool = True
    reward_risk_remaining: float | None = None
    intraday_override: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "state": self.state, "reasons": self.reasons,
                "thesis_valid": self.thesis_valid, "reward_risk_remaining": self.reward_risk_remaining,
                "intraday_override": self.intraday_override}


def deterioration_signals(f: pd.DataFrame) -> list[str]:
    """Evidence that an active long thesis is weakening, from *completed* daily data only."""
    if len(f) < 60:
        return []
    r = f.iloc[-1]
    sig = []
    for st in detect_setups(f):
        if st.direction == "bearish" and st.name in ("breakdown", "momentum_shift") and st.stage != "invalidated":
            sig.append(f"{st.name} ({st.stage}): {st.detail}")
        if st.name == "breakout" and st.stage == "invalidated":
            sig.append("failed breakout: " + st.detail)
    if np.isfinite(r.get("c_sma20", np.nan)) and r["c_sma20"] < 0 and r.get("vol_ratio20", 0) > 1.3 and r["ret_1"] < 0:
        sig.append(f"close below 20-SMA on {r['vol_ratio20']:.1f}x volume")
    if np.isfinite(r.get("rs_index20", np.nan)) and r["rs_index20"] < -0.05:
        sig.append(f"relative strength vs index deteriorated to {r['rs_index20']:+.1%}")
    return sig


def assess_position(pos: dict[str, Any], price: float, atr: float, f: pd.DataFrame | None, *,
                    intraday: bool, p_down: float | None = None) -> Assessment:
    stop, t1, t2 = pos.get("stop"), pos.get("target1"), pos.get("target2")
    prev_state = pos.get("monitor_state") or "normal"
    entry = float(pos["avg_price"])
    reasons: list[str] = []
    alerts: list[dict[str, Any]] = []
    state, action = "normal", "HOLD"
    a = atr if np.isfinite(atr) and atr > 0 else entry * 0.02
    det = deterioration_signals(f) if f is not None else []
    if p_down is not None and p_down >= 0.5:
        det.append(f"calibrated P(stop before target) {p_down:.0%}")

    if stop is not None and price <= stop:
        state, action = "stop_triggered", "EXIT"
        reasons.append(f"price {price:.2f} at/below stop {stop:.2f} — invalidation condition met")
        alerts.append({"alert_class": "stop_triggered", "stage": "confirmed",
                       "title": f"{pos['symbol']}: stop/invalidation triggered",
                       "message": f"{price:.2f} ≤ stop {stop:.2f}. Planned exit per thesis. Fill may differ on gaps.",
                       "key": f"stop:{pos['id']}:{stop}"})
    elif t2 is not None and price >= t2:
        state, action = "target2_hit", "EXIT"
        reasons.append(f"Target 2 {t2:.2f} reached")
        alerts.append({"alert_class": "target_hit", "stage": "confirmed", "title": f"{pos['symbol']}: Target 2 reached",
                       "message": f"{price:.2f} ≥ T2 {t2:.2f}. Plan: exit remaining quantity.", "key": f"t2:{pos['id']}"})
    elif t1 is not None and price >= t1:
        state, action = "target1_hit", "PARTIAL_EXIT"
        reasons.append(f"Target 1 {t1:.2f} reached")
        alerts.append({"alert_class": "target_hit", "stage": "confirmed", "title": f"{pos['symbol']}: Target 1 reached",
                       "message": f"{price:.2f} ≥ T1 {t1:.2f}.", "key": f"t1:{pos['id']}"})
        alerts.append({"alert_class": "partial_profit", "stage": "info",
                       "title": f"{pos['symbol']}: partial profit / trailing stop",
                       "message": f"Plan: book ~50% and trail stop to entry {entry:.2f}.", "key": f"trail:{pos['id']}"})
    elif stop is not None and price - stop <= max(0.5 * a, 0.3 * (entry - stop)):
        state = "approaching_stop"
        reasons.append(f"price {price:.2f} within {price - stop:.2f} of stop {stop:.2f}")
        alerts.append({"alert_class": "approaching_stop", "stage": "approaching",
                       "title": f"{pos['symbol']}: approaching stop", "key": f"near_stop:{pos['id']}:{stop}",
                       "message": f"{price:.2f} is {price - stop:.2f} above stop {stop:.2f} (not yet triggered)."})
    elif t1 is not None and t1 - price <= 0.3 * a:
        state = "approaching_target"
        reasons.append(f"price near Target 1 {t1:.2f}")
    if det and state in ("normal", "approaching_target", "approaching_stop"):
        if state == "normal":
            state = "early_warning"
        reasons += det
        alerts.append({"alert_class": "thesis_deterioration", "stage": "early_warning",
                       "title": f"{pos['symbol']}: early thesis deterioration (not a confirmed exit)",
                       "message": "; ".join(det)[:400], "key": f"det:{pos['id']}:{'|'.join(sorted(d[:20] for d in det))}"})
        if len(det) >= 2 and stop is not None and (price - stop) < a:
            action = "EXIT"
            reasons.append("multiple deterioration signals close to stop: early exit recommended")
    rr = None
    if stop is not None and t1 is not None and price > stop:
        rr = (t1 - price) / (price - stop)
        if action == "HOLD" and rr < 0.5 and state != "approaching_target":
            reasons.append(f"remaining reward/risk {rr:.2f} is poor")
    # only alert on escalation or new conditions vs previous state (hysteresis handled by dedupe keys)
    if STATE_RANK.get(state, 0) < STATE_RANK.get(prev_state, 0) and state == "normal":
        alerts = []
    return Assessment(action, state, reasons or ["thesis intact; no trigger"], alerts,
                      thesis_valid=action == "HOLD" and not det, reward_risk_remaining=rr,
                      intraday_override=intraday and action == "EXIT")
