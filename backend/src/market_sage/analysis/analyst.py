"""Senior-analyst evidence engine: turns point-in-time data into structured, traceable evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time

import numpy as np
import pandas as pd

from market_sage.analysis.analogues import AnalogueResult, find_analogues
from market_sage.analysis.evidence import Evidence, tally
from market_sage.analysis.fundamentals import fundamental_evidence
from market_sage.core.timeutil import ist_datetime
from market_sage.features.patterns import chart_patterns, flag_or_consolidation
from market_sage.features.store import FeatureStore
from market_sage.features.structure import confirmed_pivots, pivots_known_at, structure_summary

CANDLES = {
    "bullish_engulfing": "bullish",
    "hammer": "bullish",
    "morning_star": "bullish",
    "inverted_hammer": "bullish",
    "bearish_engulfing": "bearish",
    "shooting_star": "bearish",
    "evening_star": "bearish",
    "doji": "neutral",
    "marubozu": "neutral",
}


@dataclass
class AnalystReport:
    instrument_id: int
    symbol: str
    cutoff_session: date
    row: pd.Series
    evidence: list[Evidence]
    structure: dict
    patterns: list[dict]
    regime: dict
    analogues: AnalogueResult | None
    conflicts: list[str] = field(default_factory=list)

    @property
    def price(self) -> float:
        return float(self.row["close"])

    @property
    def atr(self) -> float:
        return float(self.row["atr14"])

    def stance_tally(self) -> dict[str, float]:
        return tally(self.evidence)


def _fmt(x: float, pct: bool = False) -> str:
    return "n/a" if x is None or not np.isfinite(x) else (f"{x:+.1%}" if pct else f"{x:.1f}")


class Analyst:
    def __init__(self, store: FeatureStore) -> None:
        self.store = store
        self.mds = store.mds

    def analyse(self, instrument_id: int, cutoff: date, pool: pd.DataFrame | None = None) -> AnalystReport | None:
        inst = self.mds.instruments.get(instrument_id)
        f = self.store.instrument_features(instrument_id, until=cutoff)
        if inst is None or f.empty or f["session_date"].iloc[-1] != cutoff or len(f) < 60:
            return None
        row = f.iloc[-1]
        ev: list[Evidence] = []
        as_of = str(cutoff)
        bars = f[["high", "low", "close", "open", "volume"]]
        struct = structure_summary(bars, f["atr14"])
        ev += self._structure_evidence(struct, as_of)
        ev += self._indicator_evidence(row, as_of)
        pats = self._patterns(f, row, as_of, ev)
        ev += self._volume_evidence(row, as_of)
        regime = {
            k: (None if isinstance(row.get(k), float) and not np.isfinite(row.get(k)) else row.get(k))
            for k in ("regime_trend", "regime_vol", "regime_transition", "regime_confidence")
        }
        ev += self._context_evidence(row, regime, as_of)
        known_by = ist_datetime(cutoff, time(23, 59))
        ev += fundamental_evidence(self.mds.engine, instrument_id, known_by)
        analog = None
        if pool is not None and not pool.empty:
            analog = find_analogues(
                pool,
                row,
                cutoff,
                exclude_instrument=instrument_id,
                regime=str(row.get("regime_trend")) if row.get("regime_trend") else None,
            )
        ev += self._analogue_evidence(analog, as_of)
        t = tally(ev)
        conflicts = []
        if t["bullish"] > 0 and t["bearish"] > 0:
            bear = [e.statement for e in ev if e.stance == "bearish" and e.kind != "unknown"][:3]
            bull = [e.statement for e in ev if e.stance == "bullish" and e.kind != "unknown"][:3]
            if min(t["bullish"], t["bearish"]) / max(t["bullish"], t["bearish"]) > 0.5:
                conflicts.append(
                    "Material disagreement between modules: bullish ("
                    + "; ".join(bull)
                    + ") vs bearish ("
                    + "; ".join(bear)
                    + ")."
                )
        return AnalystReport(instrument_id, inst["symbol"], cutoff, row, ev, struct, pats, regime, analog, conflicts)

    # --- evidence builders -------------------------------------------------------------------
    def _structure_evidence(self, st: dict, as_of: str) -> list[Evidence]:
        out = []
        trend = st["trend"]
        stance = {"uptrend": "bullish", "downtrend": "bearish"}.get(trend, "neutral")
        out.append(
            Evidence(
                "structure",
                "inference",
                stance,
                f"Swing structure: {trend} (confirmed pivots)",
                value=trend,
                method="3-bar confirmed pivots, last two highs/lows",
                as_of=as_of,
                weight=1.5,
            )
        )
        if st["breakout_20d"]:
            out.append(
                Evidence(
                    "structure",
                    "fact",
                    "bullish",
                    "Close above prior 20-session high (breakout)",
                    as_of=as_of,
                    weight=1.2,
                )
            )
        if st["breakdown_20d"]:
            out.append(
                Evidence(
                    "structure",
                    "fact",
                    "bearish",
                    "Close below prior 20-session low (breakdown)",
                    as_of=as_of,
                    weight=1.2,
                )
            )
        return out

    def _indicator_evidence(self, r: pd.Series, as_of: str) -> list[Evidence]:
        out = []
        c50, c200 = r.get("c_sma50"), r.get("c_sma200")
        if np.isfinite(c200):
            out.append(
                Evidence(
                    "indicators",
                    "fact",
                    "bullish" if c200 > 0 else "bearish",
                    f"Price {_fmt(c200, True)} vs 200-SMA",
                    value=float(c200),
                    method="SMA200",
                    as_of=as_of,
                )
            )
        if np.isfinite(c50):
            out.append(
                Evidence(
                    "indicators",
                    "fact",
                    "bullish" if c50 > 0 else "bearish",
                    f"Price {_fmt(c50, True)} vs 50-SMA",
                    value=float(c50),
                    method="SMA50",
                    as_of=as_of,
                    weight=0.8,
                )
            )
        rsi = r.get("rsi14")
        if np.isfinite(rsi):
            stance = "bearish" if rsi > 75 else "bullish" if 50 < rsi <= 70 else "bearish" if rsi < 40 else "neutral"
            out.append(
                Evidence(
                    "indicators",
                    "fact",
                    stance,
                    f"RSI(14) {rsi:.0f}",
                    value=float(rsi),
                    method="Wilder RSI",
                    as_of=as_of,
                    weight=0.6,
                )
            )
        mh = r.get("macd_hist_n")
        if np.isfinite(mh):
            out.append(
                Evidence(
                    "indicators",
                    "fact",
                    "bullish" if mh > 0 else "bearish",
                    f"MACD histogram {'positive' if mh > 0 else 'negative'}",
                    value=float(mh),
                    method="MACD(12,26,9)",
                    as_of=as_of,
                    weight=0.6,
                )
            )
        adx, dis = r.get("adx14"), r.get("di_spread")
        if np.isfinite(adx):
            strong = adx > 25
            stance = ("bullish" if dis > 0 else "bearish") if strong else "neutral"
            out.append(
                Evidence(
                    "indicators",
                    "fact",
                    stance,
                    f"ADX {adx:.0f} ({'trending' if strong else 'weak trend'}), DI spread {dis:+.1f}",
                    value=float(adx),
                    method="ADX(14)",
                    as_of=as_of,
                    weight=0.7,
                )
            )
        vc = r.get("vol_contraction")
        if np.isfinite(vc) and vc < 0.7:
            out.append(
                Evidence(
                    "indicators",
                    "inference",
                    "neutral",
                    f"Volatility contraction (20d/60d vol ratio {vc:.2f}) — expansion often follows",
                    value=float(vc),
                    as_of=as_of,
                    weight=0.5,
                )
            )
        return out

    def _patterns(self, f: pd.DataFrame, r: pd.Series, as_of: str, ev: list[Evidence]) -> list[dict]:
        pats: list[dict] = []
        for name, bias in CANDLES.items():
            if r.get(name, 0) == 1:
                pats.append({"name": name, "bias": bias, "confirmed": False, "type": "candle"})
                ev.append(
                    Evidence(
                        "patterns",
                        "fact",
                        bias,
                        f"Candle: {name.replace('_', ' ')} (needs confirmation)",
                        as_of=as_of,
                        weight=0.3,
                        method="candle geometry",
                    )
                )
        t = len(f) - 1
        piv = pivots_known_at(confirmed_pivots(f["high"].to_numpy(), f["low"].to_numpy(), 3), t)
        found = chart_patterns(piv[-12:], float(r["close"]), float(r["atr14"]))
        flag = flag_or_consolidation(f, f["atr14"])
        if flag:
            found.append(flag)
        for p in found:
            pats.append(
                {
                    "name": p.name,
                    "bias": p.bias,
                    "confirmed": p.confirmed,
                    "level": p.level,
                    "detail": p.detail,
                    "type": "chart",
                }
            )
            stance = p.bias if p.bias in ("bullish", "bearish") else "neutral"
            ev.append(
                Evidence(
                    "patterns",
                    "inference",
                    stance,
                    f"Chart pattern: {p.name.replace('_', ' ')} ({'confirmed' if p.confirmed else 'unconfirmed'})"
                    f" — {p.detail}",
                    value=p.level,
                    method="pivot-based detection",
                    as_of=as_of,
                    weight=1.0 if p.confirmed else 0.4,
                )
            )
        return pats

    def _volume_evidence(self, r: pd.Series, as_of: str) -> list[Evidence]:
        out = []
        vr, ret1 = r.get("vol_ratio20"), r.get("ret_1")
        if np.isfinite(vr) and vr > 1.8:
            stance = "bullish" if ret1 > 0 else "bearish"
            out.append(
                Evidence(
                    "volume",
                    "fact",
                    stance,
                    f"Volume {vr:.1f}x 20-day average on a {_fmt(ret1, True)} day",
                    value=float(vr),
                    as_of=as_of,
                    weight=0.8,
                )
            )
            out.append(
                Evidence(
                    "volume",
                    "inference",
                    "neutral",
                    "Unusual volume is not proof of institutional activity (inference only).",
                    as_of=as_of,
                    weight=0.0,
                )
            )
        dr = r.get("delivery_ratio")
        if np.isfinite(dr) and dr > 1.3:
            out.append(
                Evidence(
                    "volume",
                    "fact",
                    "bullish" if ret1 > 0 else "bearish",
                    f"Delivery % {dr:.1f}x its 20-day average",
                    value=float(dr),
                    as_of=as_of,
                    weight=0.5,
                )
            )
        elif not np.isfinite(r.get("delivery_pct", np.nan)):
            out.append(Evidence("volume", "unknown", "neutral", "Delivery data unavailable for this session."))
        obs = r.get("obv_slope20")
        if np.isfinite(obs):
            out.append(
                Evidence(
                    "volume",
                    "fact",
                    "bullish" if obs > 0 else "bearish",
                    f"OBV trend {'rising' if obs > 0 else 'falling'} over 20 sessions",
                    value=float(obs),
                    as_of=as_of,
                    weight=0.4,
                )
            )
        return out

    def _context_evidence(self, r: pd.Series, regime: dict, as_of: str) -> list[Evidence]:
        out = []
        rt = regime.get("regime_trend")
        if rt and rt != "unknown":
            stance = {"bull": "bullish", "bear": "bearish"}.get(str(rt), "neutral")
            conf = regime.get("regime_confidence") or 0
            out.append(
                Evidence(
                    "context",
                    "estimate",
                    stance,
                    f"Market regime: {rt}/{regime.get('regime_vol')}"
                    f"{' (transition)' if regime.get('regime_transition') else ''}, confidence {conf:.2f}",
                    value=rt,
                    method="index trend/volatility heuristic",
                    as_of=as_of,
                    weight=1.0,
                )
            )
        else:
            out.append(Evidence("context", "unknown", "neutral", "Market regime unknown (insufficient index history)."))
        for col, label in (("rs_index20", "index"), ("rs_sector20", "sector")):
            v = r.get(col)
            if np.isfinite(v):
                out.append(
                    Evidence(
                        "context",
                        "fact",
                        "bullish" if v > 0 else "bearish",
                        f"20-session relative strength vs {label}: {_fmt(v, True)}",
                        value=float(v),
                        as_of=as_of,
                        weight=0.8,
                    )
                )
        idx = r.get("index_ret20")
        if np.isfinite(idx) and np.isfinite(r.get("ret_20")):
            own = r["ret_20"] - idx
            kind = "company-specific" if abs(own) > abs(idx) else "market-driven"
            out.append(
                Evidence(
                    "context",
                    "inference",
                    "neutral",
                    f"Recent move looks {kind} (stock {_fmt(r['ret_20'], True)} vs index {_fmt(idx, True)})",
                    as_of=as_of,
                    weight=0.0,
                )
            )
        return out

    def _analogue_evidence(self, a: AnalogueResult | None, as_of: str) -> list[Evidence]:
        if a is None or 5 not in a.by_horizon:
            return [Evidence("analogues", "unknown", "neutral", "Insufficient point-in-time history for analogues.")]
        h5 = a.by_horizon[5]
        stance = (
            "bullish"
            if h5["median"] > 0.005 and h5["win_rate"] > 0.55
            else "bearish"
            if h5["median"] < -0.005 and h5["win_rate"] < 0.45
            else "neutral"
        )
        return [
            Evidence(
                "analogues",
                "estimate",
                stance,
                f"{a.sample_size} historical analogues: 5-session median {h5['median']:+.1%}, "
                f"win rate {h5['win_rate']:.0%}, P10/P90 {h5['p10']:+.1%}/{h5['p90']:+.1%}",
                value=h5,
                method=a.method,
                as_of=as_of,
                weight=1.0,
                meta={"period": a.period, "regime_matched": a.regime_matched},
            )
        ]


def cutoff_datetime(session: date) -> datetime:
    """Decision timestamp convention for EOD forecasts: after the 15:30 IST close of ``session``."""
    return ist_datetime(session, time(15, 30))
