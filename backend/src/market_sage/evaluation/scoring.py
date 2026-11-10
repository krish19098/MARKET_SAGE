"""Prediction scoring at multiple horizons and at trade closure, using only data after the decision.

Scores are kept separate (direction, entry timing, target, stop quality, calibration, net outcome); there is
no single flattering score. Counterfactual values are labelled as such.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, insert, select

from market_sage.core.timeutil import IST, utcnow
from market_sage.data.service import MarketDataService
from market_sage.db import schema as s
from market_sage.features.store import FeatureStore
from market_sage.monitoring.rules import deterioration_signals

HORIZONS = (1, 3, 5, 10, 20)
ERROR_CAUSES = ("data", "feature", "regime", "model", "execution", "risk", "event", "unknown")


def session_of(cutoff: datetime) -> date:
    return cutoff.astimezone(IST).date()


def path_after(mds: MarketDataService, pred: dict, n: int) -> pd.DataFrame:
    bars = mds.daily_bars(pred["instrument_id"])
    return bars[bars["session_date"] > session_of(pred["data_cutoff"])].head(n).reset_index(drop=True)


def score_prediction(pred: dict, path: pd.DataFrame, horizon: int) -> dict[str, Any] | None:
    """Score a prediction over the first ``horizon`` sessions of ``path``; None if not yet complete."""
    if len(path) < horizon:
        return None
    p = path.head(horizon)
    ref = float(pred["price_at_prediction"])
    close_h = float(p["close"].iloc[-1])
    ret = close_h / ref - 1
    out: dict[str, Any] = {"horizon_sessions": horizon, "close": close_h, "return": ret,
                           "mfe": float(p["high"].max() / ref - 1), "mae": float(p["low"].min() / ref - 1),
                           "last_session": str(p["session_date"].iloc[-1])}
    action = pred["action"]
    if action == "BUY":
        out["direction_correct"] = bool(ret > 0)
        el, eh = pred["entry_low"], pred["entry_high"]
        first = p.iloc[0]
        filled = first["open"] <= eh or first["low"] <= eh
        fill = float(first["open"]) if first["open"] <= eh else float(eh) if first["low"] <= eh else None
        out["entry"] = {"filled_next_session": bool(filled), "assumed_fill": fill,
                        "gap_above_range": bool(first["open"] > eh),
                        "entry_vs_best_low_3s": None if fill is None else float(fill / p["low"].head(3).min() - 1),
                        "within_range": bool(fill is not None and el <= fill <= eh)}
        stop, t1, t2 = pred["stop"], pred["target1"], pred["target2"]
        hit_stop = p.index[p["low"] <= stop]
        hit_t1 = p.index[p["high"] >= t1]
        hit_t2 = p.index[p["high"] >= t2]
        first_stop = int(hit_stop[0]) if len(hit_stop) else None
        first_t1 = int(hit_t1[0]) if len(hit_t1) else None
        if first_stop is not None and (first_t1 is None or first_stop <= first_t1):
            barrier = "stop"
        elif first_t1 is not None:
            barrier = "target1"
        else:
            barrier = "timeout"
        out["barrier_outcome"] = barrier
        out["target"] = {"t1_hit": first_t1 is not None, "t1_session": first_t1, "t2_hit": bool(len(hit_t2)),
                         "t2_session": int(hit_t2[0]) if len(hit_t2) else None}
        recovered = bool(barrier == "stop" and p["high"].iloc[first_stop:].max() >= t1) if first_stop is not None else False
        out["stop_quality"] = {"stopped": first_stop is not None, "stopped_then_reached_t1": recovered,
                               "stop_distance_atr_mult": None}
        probs = pred.get("probabilities")
        if probs:
            y = {"target1": 1, "stop": -1, "timeout": 0}[barrier]
            onehot = {"up": float(y == 1), "neutral": float(y == 0), "down": float(y == -1)}
            out["brier"] = float(sum((probs[k] - onehot[k]) ** 2 for k in onehot))
            out["log_loss"] = float(-np.log(max(probs[{1: "up", 0: "neutral", -1: "down"}[y]], 1e-6)))
            out["p_up"] = float(probs["up"])
            out["y_up"] = int(y == 1)
    else:  # AVOID / suppressed: measure what was missed or avoided (counterfactual)
        out["missed_upside"] = max(0.0, out["mfe"])
        out["avoided_downside"] = max(0.0, -out["mae"])
        out["direction_correct"] = bool(ret <= 0)
    return out


def classify_error(pred: dict, score: dict, regime_changed: bool, gap_atr: float | None) -> str:
    if pred.get("data_status") in ("stale",):
        return "data"
    if pred["action"] != "BUY":
        return "unknown"
    if score.get("entry", {}).get("gap_above_range"):
        return "execution"
    if gap_atr is not None and gap_atr > 3:
        return "event"
    if score.get("stop_quality", {}).get("stopped_then_reached_t1"):
        return "risk"
    if regime_changed:
        return "regime"
    if score.get("barrier_outcome") == "stop" and (score.get("p_up") or 0) >= 0.5:
        return "model"
    return "unknown"


class Evaluator:
    def __init__(self, mds: MarketDataService, store: FeatureStore) -> None:
        self.mds, self.store = mds, store
        self.engine: Engine = mds.engine

    def _done(self) -> set[tuple[str, str]]:
        with self.engine.connect() as conn:
            return {(r.prediction_id, r.horizon) for r in conn.execute(
                select(s.evaluations.c.prediction_id, s.evaluations.c.horizon))}

    def evaluate_pending(self, now: datetime | None = None) -> int:
        """Score every prediction at every horizon whose data is complete; append-only, idempotent."""
        now = now or utcnow()
        done = self._done()
        with self.engine.connect() as conn:
            preds = [dict(r._mapping) for r in conn.execute(select(s.predictions).order_by(s.predictions.c.seq))]
        n = 0
        for pred in preds:
            path = path_after(self.mds, pred, max(HORIZONS))
            for h in HORIZONS:
                key = f"{h}s"
                if (pred["id"], key) in done:
                    continue
                sc = score_prediction(pred, path, h)
                if sc is None:
                    continue
                last = path["source_ts"].iloc[h - 1]
                with self.engine.begin() as conn:
                    conn.execute(insert(s.evaluations).values(prediction_id=pred["id"], horizon=key, evaluated_at=now,
                                                              data_cutoff=last, metrics=_clean(sc)))
                n += 1
                if h == 5 and pred["action"] == "BUY":
                    self._lesson(pred, sc, path, now)
        return n

    def _lesson(self, pred: dict, sc: dict, path: pd.DataFrame, now: datetime) -> None:
        f = self.store.instrument_features(pred["instrument_id"])
        dec = session_of(pred["data_cutoff"])
        win = f[(f["session_date"] >= dec)].head(6)
        regime_changed = bool(win["regime_trend"].nunique() > 1) if "regime_trend" in win else False
        atr = float(f.loc[f["session_date"] == dec, "atr14"].iloc[0]) if (f["session_date"] == dec).any() else None
        gaps = (path["open"].head(5) - path["close"].shift(1).fillna(pred["price_at_prediction"]).head(5)).abs()
        gap_atr = float(gaps.max() / atr) if atr else None
        cause = classify_error(pred, sc, regime_changed, gap_atr)
        correct = [e["statement"] for e in pred["evidence"] if e["stance"] == "bullish"] if sc["return"] > 0 else \
            [e["statement"] for e in pred["evidence"] if e["stance"] == "bearish"]
        wrong = [e["statement"] for e in pred["evidence"] if e["stance"] == ("bearish" if sc["return"] > 0 else "bullish")]
        a = pred["thesis"].get("10_expected_return_and_downside")
        analog_vs = None
        if isinstance(a, dict):
            analog_vs = {"expected_median": a.get("median"), "actual": sc["return"],
                         "inside_p10_p90": bool(a.get("p10", -1) <= sc["return"] <= a.get("p90", 1))}
        payload = {"outcome": sc.get("barrier_outcome"), "return_5s": sc["return"], "assumptions_correct": correct[:5],
                   "assumptions_incorrect": wrong[:5], "analogue_vs_actual": analog_vs, "regime_changed": regime_changed,
                   "max_gap_atr": gap_atr,
                   "timing": "entry missed (gap above range)" if sc.get("entry", {}).get("gap_above_range") else
                   ("stopped then recovered — stop likely too tight" if cause == "risk" else "n/a"),
                   "candidate_improvement": {"data": "improve data freshness checks", "execution": "review entry rule for gaps",
                                             "event": "add event/gap-risk filter", "risk": "test wider/structural stops",
                                             "regime": "regime-conditioned model or filter",
                                             "model": "feature/model review in next candidate cycle",
                                             "unknown": "insufficient evidence; keep monitoring"}[cause]}
        with self.engine.begin() as conn:
            conn.execute(insert(s.lessons).values(prediction_id=pred["id"], created_at=now, error_cause=cause,
                                                  payload=_clean(payload)))

    # --- exit evaluation -----------------------------------------------------------------------
    def evaluate_exit(self, pred: dict, exit_price: float, exit_session: date, sessions_after: int = 10,
                      actual_fill: float | None = None, entry_price: float | None = None) -> dict[str, Any] | None:
        bars = self.mds.daily_bars(pred["instrument_id"])
        after = bars[bars["session_date"] > exit_session].head(sessions_after)
        if after.empty:
            return None
        lo, hi, last = float(after["low"].min()), float(after["high"].max()), float(after["close"].iloc[-1])
        basis = actual_fill if actual_fill is not None else exit_price
        res: dict[str, Any] = {
            "exit_recommendation_price": exit_price, "actual_fill": actual_fill,
            "basis": "confirmed user fill" if actual_fill is not None else "COUNTERFACTUAL: assumes execution at the recommended exit price",
            "sessions_observed": int(len(after)),
            "max_adverse_move_avoided_per_share": max(0.0, basis - lo),
            "potential_upside_missed_per_share": max(0.0, hi - basis),
            "net_impact_per_share_vs_holding": basis - last,
            "lowest_after": lo, "highest_after": hi, "close_after": last,
            "entry_price": entry_price,
        }
        res["earlier_warning"] = self.earlier_warning_possible(pred, exit_session)
        if entry_price and pred.get("target1") and pred.get("stop"):
            res["alternative_trailing"] = self._trailing_alternative(pred, entry_price, exit_session, bars)
        return res

    def earlier_warning_possible(self, pred: dict, exit_session: date) -> dict[str, Any]:
        """Replay sessions between decision and exit with point-in-time features only."""
        start = session_of(pred["data_cutoff"])
        full = self.mds.daily_bars(pred["instrument_id"])
        sessions = [d for d in full["session_date"] if start < d < exit_session]
        for d in sessions:
            f = self.store.instrument_features(pred["instrument_id"], until=d)
            sig = deterioration_signals(f)
            if sig:
                return {"possible": True, "first_session": str(d), "signals": sig,
                        "note": "derived only from data available at that session"}
        return {"possible": False, "note": "no deterioration signal in point-in-time data before the exit"}

    @staticmethod
    def _trailing_alternative(pred: dict, entry: float, exit_session: date, bars: pd.DataFrame) -> dict[str, Any]:
        """Alternative: book 50% at T1, trail the rest at entry; compare per-share outcome (counterfactual)."""
        p = bars[bars["session_date"] > session_of(pred["data_cutoff"])].head(20)
        t1, stop = pred["target1"], pred["stop"]
        half_done, trail, out = False, stop, None
        for _, r in p.iterrows():
            if r["low"] <= trail:
                px = min(r["open"], trail)
                out = (0.5 * (t1 - entry) + 0.5 * (px - entry)) if half_done else (px - entry)
                break
            if not half_done and r["high"] >= t1:
                half_done, trail = True, entry
        if out is None:
            last = float(p["close"].iloc[-1]) if len(p) else entry
            out = (0.5 * (t1 - entry) + 0.5 * (last - entry)) if half_done else last - entry
        return {"per_share": float(out), "rule": "50% at T1, trail rest to entry (counterfactual)"}


def _clean(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_clean(v) for v in x]
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, float | np.floating):
        return None if not np.isfinite(x) else float(x)
    return x
