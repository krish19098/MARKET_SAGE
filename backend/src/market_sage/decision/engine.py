"""Decision & risk layer: converts analysis + calibrated forecasts into BUY/AVOID recommendations with a
complete trade plan, or suppresses them with explicit reasons.

A forecast alone never creates a trade: the suppression gate, model-skill requirement, expected value
net of costs, reward/risk and evidence balance must all pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from market_sage.analysis.analyst import AnalystReport
from market_sage.analysis.evidence import Evidence
from market_sage.data.models import DataStatus
from market_sage.models.registry import TrainedModel
from market_sage.models.setups import Setup
from market_sage.portfolio.costs import CostModel
from market_sage.portfolio.risk import RiskSettings

STRATEGY_VERSION = "swing-eod-v1"
FRESH_STATUSES = {DataStatus.EOD, DataStatus.LIVE, DataStatus.SYNTHETIC, DataStatus.DELAYED}


@dataclass
class ModelContext:
    model: TrainedModel | None
    has_skill: bool
    skill_note: str


@dataclass
class TradePlan:
    entry_low: float
    entry_high: float
    stop: float
    target1: float
    target2: float
    horizon_sessions: int
    horizon_range: tuple[int, int]
    reward_risk_t1: float
    per_share_risk: float
    entry_rule: str
    partial_booking: str
    gap_risk_note: str

    def to_dict(self) -> dict:
        return self.__dict__ | {"horizon_range": list(self.horizon_range)}


@dataclass
class Recommendation:
    instrument_id: int
    symbol: str
    action: str
    direction: str
    price: float
    data_status: str
    plan: TradePlan | None
    probabilities: dict[str, float] | None
    calibration_status: str
    expected_value_per_share: float | None
    quality_score: float | None
    suppressed: bool
    reasons: list[str]
    evidence: list[Evidence]
    thesis: dict[str, Any]
    setups: list[Setup]
    liquidity: dict[str, float]
    model_version: str | None
    report: AnalystReport | None = field(repr=False, default=None)

    @property
    def kind(self) -> str:
        return "suppressed" if self.suppressed else "recommendation"


def liquidity_stats(f: pd.DataFrame) -> dict[str, float]:
    tail = f.tail(20)
    turnover = (tail["close"] * tail["volume"]).median()
    return {
        "median_turnover_20d": float(turnover),
        "adv_20d": float(tail["volume"].mean()),
        "price": float(f["close"].iloc[-1]),
    }


def model_context(model: TrainedModel | None) -> ModelContext:
    if model is None:
        return ModelContext(None, False, "no production model; probabilities not issued")
    m = model.metrics
    sel = m.get("selected", model.algorithm)
    summ = m.get("walk_forward", {}).get("summary", {})
    if sel == "climatology" or sel not in summ or "climatology" not in summ:
        return ModelContext(model, False, "production model shows no out-of-sample skill over climatology")
    bss = 1 - summ[sel]["brier_mean"] / summ["climatology"]["brier_mean"]
    util = summ[sel]["utility"]
    if bss <= 0 or util.get("trades", 0) < 30 or util.get("mean_net", 0) <= 0:
        return ModelContext(
            model,
            False,
            f"insufficient validated edge (Brier skill {bss:+.3f}, OOS net/trade {util.get('mean_net', 0):+.4f})",
        )
    return ModelContext(
        model,
        True,
        f"OOS Brier skill {bss:+.3f}; OOS net/trade {util['mean_net']:+.4f} over "
        f"{util['trades']} trades{' — SYNTHETIC data' if model.is_synthetic_data else ''}",
    )


def build_plan(report: AnalystReport, model: TrainedModel | None) -> TradePlan | None:
    price, atr = report.price, report.atr
    if not (np.isfinite(atr) and atr > 0 and price > 0):
        return None
    c = (model.contract if model else {}) or {}
    up_k, dn_k, h = c.get("upper_atr", 1.5), c.get("lower_atr", 1.0), c.get("horizon_sessions", 5)
    entry_low, entry_high = price - 0.2 * atr, price + 0.2 * atr
    ref = price
    stop = ref - dn_k * atr
    t1 = ref + up_k * atr
    res = report.structure.get("resistance")
    t2 = max(ref + 3.0 * atr, res["low"]) if res and res["low"] > t1 else ref + 3.0 * atr
    rr = (t1 - ref) / (ref - stop)
    return TradePlan(
        round(entry_low, 2),
        round(entry_high, 2),
        round(stop, 2),
        round(t1, 2),
        round(t2, 2),
        h,
        (max(1, h - 2), h * 2),
        round(rr, 2),
        round(ref - stop, 2),
        "Enter next session only within the entry range; skip if it opens above the range (no chasing).",
        "Book ~50% at Target 1 and trail the stop to entry; exit the rest at Target 2 or on invalidation.",
        "Stops can fill worse than planned on gaps or thin liquidity; loss at stop is an estimate.",
    )


def decide(
    report: AnalystReport,
    data_status: DataStatus,
    mctx: ModelContext,
    settings: RiskSettings,
    costs: CostModel,
    setups: list[Setup],
    liquidity: dict[str, float],
    features_complete: bool = True,
) -> Recommendation:
    reasons: list[str] = []
    # --- suppression gate (data/feasibility) ---
    if data_status not in FRESH_STATUSES:
        reasons.append(f"data status '{data_status.value}': latest session data missing or stale")
    if not features_complete:
        reasons.append("critical features could not be computed")
    if liquidity["price"] < settings.min_price:
        reasons.append(f"price below ₹{settings.min_price:.0f} floor (penny-stock filter)")
    if liquidity["median_turnover_20d"] < settings.min_median_turnover:
        reasons.append(
            f"illiquid: 20-day median turnover ₹{liquidity['median_turnover_20d'] / 1e7:.1f} cr below "
            f"₹{settings.min_median_turnover / 1e7:.0f} cr"
        )
    plan = build_plan(report, mctx.model)
    if plan is None:
        reasons.append("risk cannot be calculated (ATR/price unavailable)")
    suppressed = bool(reasons)

    probs, cal_status, ev, q = None, "not_issued", None, None
    action, direction = "AVOID", "neutral"
    if not suppressed and plan is not None:
        if mctx.model is not None:
            p = mctx.model.proba_dict(report.row)
            cal_ok = mctx.has_skill
            probs = p if cal_ok else None
            cal_status = "calibrated_oos" if cal_ok else "withheld_no_skill"
            direction = max(p, key=lambda k: p[k]) if cal_ok else "neutral"
            if cal_ok:
                gain, loss = plan.target1 - report.price, report.price - plan.stop
                per_share_cost = costs.round_trip(report.price, plan.target1, 100) / 100
                ev = p["up"] * gain - p["down"] * loss - per_share_cost
                q = ev / plan.per_share_risk
        tally = report.stance_tally()
        if not mctx.has_skill:
            reasons.append(f"no validated predictive edge: {mctx.skill_note}")
        elif probs and probs["up"] < settings.min_p_up:
            reasons.append(f"calibrated P(target before stop) {probs['up']:.0%} below {settings.min_p_up:.0%}")
        elif ev is not None and ev <= 0:
            reasons.append(f"expected value after costs is not positive (₹{ev:.2f}/share)")
        elif plan.reward_risk_t1 < settings.min_reward_risk:
            reasons.append(f"reward/risk {plan.reward_risk_t1:.2f} below {settings.min_reward_risk}")
        elif tally["bearish"] > tally["bullish"] * 1.25:
            reasons.append("weight of evidence is bearish despite model estimate")
        elif any(s.stage == "invalidated" and s.direction == "bullish" for s in setups):
            reasons.append("bullish setup recently invalidated (failed breakout)")
        else:
            action = "BUY"
    rec = Recommendation(
        report.instrument_id,
        report.symbol,
        action,
        direction,
        report.price,
        data_status.value,
        plan,
        probs,
        cal_status,
        ev,
        q,
        suppressed,
        reasons,
        report.evidence,
        {},
        setups,
        liquidity,
        mctx.model.version if mctx.model else None,
        report,
    )
    rec.thesis = build_thesis(rec, mctx)
    return rec


def build_thesis(rec: Recommendation, mctx: ModelContext) -> dict[str, Any]:
    """The 13-part analyst thesis. Every statement traces to evidence or explicit unknowns."""
    rep = rec.report
    assert rep is not None
    by_cat: dict[str, list[str]] = {}
    for e in rep.evidence:
        by_cat.setdefault(e.category, []).append(f"[{e.kind}] {e.statement}")
    bull = [e.statement for e in rep.evidence if e.stance == "bullish" and e.kind != "unknown"]
    bear = [e.statement for e in rep.evidence if e.stance == "bearish" and e.kind != "unknown"]
    plan = rec.plan
    a = rep.analogues
    analog_txt = (
        "insufficient history"
        if a is None
        else f"{a.sample_size} analogues ({a.method}); period {a.period[0]}→{a.period[1]}"
        f"{'; regime-matched' if a.regime_matched else ''}"
        if a.period
        else "n/a"
    )
    exp_range = None
    if a is not None and 5 in a.by_horizon:
        h5 = a.by_horizon[5]
        exp_range = {
            "horizon_sessions": 5,
            "p10": h5["p10"],
            "median": h5["median"],
            "p90": h5["p90"],
            "source": "historical analogues (estimate)",
        }
    return {
        "1_market_sector_context": by_cat.get("context", []),
        "2_fundamentals_valuation": by_cat.get("fundamentals", []),
        "3_technical_structure": by_cat.get("structure", []) + by_cat.get("indicators", []),
        "4_volume_liquidity": by_cat.get("volume", [])
        + [f"[fact] 20-day median turnover ₹{rec.liquidity['median_turnover_20d'] / 1e7:.1f} cr"],
        "5_historical_analogues": [analog_txt] + by_cat.get("analogues", []),
        "6_bullish_scenario": bull[:6] or ["No material bullish evidence."],
        "7_bearish_scenario": bear[:6] or ["No material bearish evidence."],
        "8_neutral_scenario": [
            "Range-bound drift with neither target nor stop reached within the horizon (time-out outcome)."
        ],
        "9_catalysts_events": ["No verified upcoming corporate events ingested."],
        "10_expected_return_and_downside": exp_range or "unknown (insufficient analogue history)",
        "11_trade_plan": plan.to_dict() if plan else "not available",
        "12_what_changes_view": (
            [
                f"Daily close below ₹{plan.stop:.2f} (invalidation)",
                "Confirmed breakdown below 20-session low or market regime turning bear",
                "Data becoming stale / feed outage (recommendation suspended)",
            ]
            if plan
            else []
        ),
        "13_why_selected": rec.reasons
        if rec.action != "BUY"
        else [
            f"Calibrated P(target first) {rec.probabilities['up']:.0%}" if rec.probabilities else "",
            f"Expected value after costs ₹{rec.expected_value_per_share:.2f}/share"
            if rec.expected_value_per_share
            else "",
            f"Model: {mctx.skill_note}",
        ],
        "conflicts": rep.conflicts,
        "model": mctx.skill_note,
    }
