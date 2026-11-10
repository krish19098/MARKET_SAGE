"""Performance & accountability aggregation for the Performance screen.

Simulated/counterfactual values are always labelled separately from confirmed user P&L. Every rate is
reported with its sample size and a confidence interval where meaningful.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import Engine, select

from market_sage.core.timeutil import utcnow
from market_sage.db import schema as s
from market_sage.notifications.alerts import AlertStore

ASPIRATION_PER_DAY = 500.0
SESSIONS_PER_YEAR = 245


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def bootstrap_ci(x: np.ndarray, n_boot: int = 1000, seed: int = 0) -> list[float] | None:
    if len(x) < 5:
        return None
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def rate(k: int, n: int) -> dict[str, Any]:
    return {"value": (k / n) if n else None, "n": n, "ci95": wilson(k, n)}


def aspiration_requirements(capital_options: tuple[int, ...] = (20000, 50000, 100000, 250000, 500000)) -> list[dict]:
    yearly = ASPIRATION_PER_DAY * SESSIONS_PER_YEAR
    return [{"capital": c, "required_annual_return": yearly / c, "required_daily_return": ASPIRATION_PER_DAY / c}
            for c in capital_options]


class PerformanceService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def evaluate_alerts(self, now: datetime | None = None, window: timedelta = timedelta(days=14)) -> int:
        """Resolve early/approaching alerts: did the anticipated confirmed event follow within the window?"""
        now = now or utcnow()
        store = AlertStore(self.engine)
        with self.engine.connect() as conn:
            alerts = [dict(r._mapping) for r in conn.execute(select(s.alerts).order_by(s.alerts.c.created_at))]
            resolved = {r.alert_id for r in conn.execute(select(s.alert_outcomes.c.alert_id))}
        confirmed = [a for a in alerts if a["stage"] == "confirmed"]
        n = 0
        for a in alerts:
            if a["id"] in resolved or a["stage"] not in ("early_warning", "approaching"):
                continue
            follow = next((c for c in confirmed if c["created_at"] > a["created_at"]
                           and c["created_at"] <= a["created_at"] + window
                           and ((a["position_id"] and c["position_id"] == a["position_id"])
                                or (not a["position_id"] and c["instrument_id"] == a["instrument_id"]))), None)
            if follow is not None:
                store.record_outcome(a["id"], "occurred", follow["created_at"],
                                     {"confirmed_alert_id": follow["id"], "class": follow["alert_class"]})
                n += 1
            elif now > a["created_at"] + window:
                store.record_outcome(a["id"], "not_occurred", None, {"window_days": window.days})
                n += 1
        return n

    def summary(self) -> dict[str, Any]:
        with self.engine.connect() as conn:
            preds = {r.id: dict(r._mapping) for r in conn.execute(select(s.predictions))}
            evals = [dict(r._mapping) for r in conn.execute(select(s.evaluations))]
            lessons = [dict(r._mapping) for r in conn.execute(select(s.lessons))]
            outcomes = [dict(r._mapping) for r in conn.execute(select(s.alert_outcomes))]
            alerts = {r.id: dict(r._mapping) for r in conn.execute(select(s.alerts))}
            events = [dict(r._mapping) for r in conn.execute(select(s.prediction_events).where(
                s.prediction_events.c.event_type == "evaluation"))]
            positions = [dict(r._mapping) for r in conn.execute(select(s.positions).where(s.positions.c.status == "closed"))]
            fills = [dict(r._mapping) for r in conn.execute(select(s.paper_fills).where(s.paper_fills.c.status == "filled"))]
            models = [dict(r._mapping) for r in conn.execute(select(s.model_registry).order_by(s.model_registry.c.id.desc()))]
        by_h: dict[str, list[dict]] = {}
        for e in evals:
            by_h.setdefault(e["horizon"], []).append(e)
        horizons = {}
        for h, rows in sorted(by_h.items(), key=lambda kv: int(kv[0].rstrip("s"))):
            buys = [r for r in rows if preds[r["prediction_id"]]["action"] == "BUY"]
            avoids = [r for r in rows if preds[r["prediction_id"]]["action"] != "BUY"]
            dir_k = sum(1 for r in buys if r["metrics"].get("direction_correct"))
            briers = np.array([r["metrics"]["brier"] for r in buys if r["metrics"].get("brier") is not None])
            rets = np.array([r["metrics"]["return"] for r in buys])
            horizons[h] = {
                "buy_direction_accuracy": rate(dir_k, len(buys)),
                "buy_mean_return_gross": {"value": float(rets.mean()) if len(rets) else None, "n": len(rets),
                                          "ci95": bootstrap_ci(rets)},
                "brier": {"value": float(briers.mean()) if len(briers) else None, "n": len(briers),
                          "ci95": bootstrap_ci(briers)},
                "entry_fill_rate": rate(sum(1 for r in buys if r["metrics"].get("entry", {}).get("filled_next_session")),
                                        len(buys)),
                "gap_missed_entries": rate(sum(1 for r in buys if r["metrics"].get("entry", {}).get("gap_above_range")),
                                           len(buys)),
                "target1_hit_rate": rate(sum(1 for r in buys if r["metrics"].get("target", {}).get("t1_hit")), len(buys)),
                "stop_rate": rate(sum(1 for r in buys if r["metrics"].get("stop_quality", {}).get("stopped")), len(buys)),
                "stopped_then_recovered": rate(sum(1 for r in buys
                                                   if r["metrics"].get("stop_quality", {}).get("stopped_then_reached_t1")),
                                               len(buys)),
                "avoid_missed_upside_mean": float(np.mean([r["metrics"]["missed_upside"] for r in avoids])) if avoids else None,
                "avoid_count": len(avoids),
            }
        calib = self._calibration([r for r in by_h.get("5s", []) if r["metrics"].get("p_up") is not None])
        early = [o for o in outcomes if alerts.get(o["alert_id"], {}).get("stage") in ("early_warning", "approaching")]
        occurred = [o for o in early if o["outcome"] == "occurred"]
        lead = [(o["event_time"] - alerts[o["alert_id"]]["created_at"]).total_seconds() / 3600 for o in occurred
                if o["event_time"]]
        exit_evals = [e["payload"] for e in events if e["payload"].get("kind") == "exit"]
        regimes: dict[str, list[float]] = {}
        model_perf: dict[str, list[float]] = {}
        for r in by_h.get("5s", []):
            p = preds[r["prediction_id"]]
            if p["action"] != "BUY":
                continue
            reg = next((e["value"] for e in p["evidence"] if e["category"] == "context" and e["kind"] == "estimate"), "unknown")
            regimes.setdefault(str(reg), []).append(r["metrics"]["return"])
            model_perf.setdefault(p["model_version"] or "none", []).append(r["metrics"]["return"])
        five = sorted([r for r in by_h.get("5s", []) if preds[r["prediction_id"]]["action"] == "BUY"],
                      key=lambda r: r["metrics"]["return"])
        ex = lambda r: {"prediction_id": r["prediction_id"], "symbol": preds[r["prediction_id"]]["symbol"],  # noqa: E731
                        "created_at": preds[r["prediction_id"]]["created_at"], "return_5s": r["metrics"]["return"],
                        "outcome": r["metrics"].get("barrier_outcome")}
        actual = [p for p in positions if p["kind"] == "actual"]
        paper = [p for p in positions if p["kind"] == "paper"]
        pnl = lambda ps: float(sum((p["exit_price"] - p["avg_price"]) * p["quantity"] - p["entry_costs"]  # noqa: E731
                                   - (p["exit_costs"] or 0) for p in ps))
        return {
            "generated_at": utcnow(),
            "counts": {"predictions": len(preds), "buy": sum(1 for p in preds.values() if p["action"] == "BUY"),
                       "suppressed": sum(1 for p in preds.values() if p["kind"] == "suppressed"),
                       "evaluations": len(evals)},
            "by_horizon": horizons,
            "calibration_5s": calib,
            "early_warning": {"resolved": len(early), "false_alert_rate": rate(len(early) - len(occurred), len(early)),
                              "median_lead_time_hours": float(np.median(lead)) if lead else None},
            "exits_counterfactual": {
                "label": "COUNTERFACTUAL — assumes execution at recommended exit prices unless a user fill is recorded",
                "n": len(exit_evals),
                "potential_loss_avoided_per_share_total": float(sum(e["max_adverse_move_avoided_per_share"] for e in exit_evals)),
                "potential_upside_missed_per_share_total": float(sum(e["potential_upside_missed_per_share"] for e in exit_evals)),
                "net_value_added_per_share_total": float(sum(e["net_impact_per_share_vs_holding"] for e in exit_evals))},
            "by_regime_5s": {k: {"mean_return": float(np.mean(v)), "n": len(v)} for k, v in regimes.items()},
            "by_model_version_5s": {k: {"mean_return": float(np.mean(v)), "n": len(v)} for k, v in model_perf.items()},
            "lessons_by_cause": {c: sum(1 for x in lessons if x["error_cause"] == c) for c in
                                 sorted({x["error_cause"] for x in lessons})},
            "examples": {"best": [ex(r) for r in five[-3:][::-1]], "worst": [ex(r) for r in five[:3]]},
            "pnl": {"confirmed_user_pnl": {"value": pnl(actual), "n": len(actual), "label": "CONFIRMED (user-entered fills)"},
                    "paper_pnl": {"value": self._paper_pnl(fills, {p["id"] for p in paper}), "n": len(paper),
                                  "label": "SIMULATED (paper trading)"}},
            "models": [{"version": m["version"], "status": m["status"], "algorithm": m["algorithm"],
                        "synthetic": m["is_synthetic_data"], "created_at": m["created_at"],
                        "gate": m["gate_report"]} for m in models[:10]],
            "aspiration": {"target_per_day": ASPIRATION_PER_DAY, "note": "Aspirational evaluation objective only — "
                           "never a promise and never a reason to force trades.",
                           "requirements": aspiration_requirements()},
        }

    @staticmethod
    def _paper_pnl(fills: list[dict], closed_ids: set[int]) -> float:
        total = 0.0
        for f in fills:
            if f["position_id"] in closed_ids:
                sign = 1 if f["side"] == "SELL" else -1
                total += sign * f["fill_price"] * f["quantity"] - (f["costs"] or 0.0)
        return float(total)

    @staticmethod
    def _calibration(rows: list[dict]) -> dict[str, Any]:
        if not rows:
            return {"n": 0, "bins": []}
        p = np.array([r["metrics"]["p_up"] for r in rows])
        y = np.array([r["metrics"]["y_up"] for r in rows])
        from market_sage.models.calibration import reliability

        return reliability(p, y.astype(float), bins=5)
