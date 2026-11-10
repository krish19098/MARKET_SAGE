"""Data-quality checks for canonical bars. Gaps are flagged, never silently filled."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from market_sage.core.calendar import ExchangeCalendar


@dataclass(frozen=True)
class QualityIssue:
    check: str
    severity: str  # info | warn | error
    trade_date: date | None
    detail: str


def check_daily_bars(
    bars: pd.DataFrame,
    calendar: ExchangeCalendar,
    known_action_dates: set[date] | None = None,
    extreme_move: float = 0.25,
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if bars.empty:
        return issues
    df = bars.sort_values("ts")
    if not bars["ts"].is_monotonic_increasing:
        issues.append(QualityIssue("out_of_order", "warn", None, "bars were not in timestamp order"))
    dups = df[df["session_date"].duplicated(keep=False)]
    for d in sorted(set(dups["session_date"])):
        issues.append(QualityIssue("duplicate", "error", d, "duplicate bars for session"))
    bad_ohlc = df[
        (df["low"] > df[["open", "close"]].min(axis=1) + 1e-9)
        | (df["high"] < df[["open", "close"]].max(axis=1) - 1e-9)
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    ]
    for d in bad_ohlc["session_date"]:
        issues.append(QualityIssue("ohlc_inconsistent", "error", d, "OHLC values inconsistent or non-positive"))
    for d in df.loc[df["volume"] < 0, "session_date"]:
        issues.append(QualityIssue("negative_volume", "error", d, "negative volume"))
    for d in df.loc[df["volume"] == 0, "session_date"]:
        issues.append(QualityIssue("zero_volume", "warn", d, "no trades recorded"))
    sessions = list(df["session_date"])
    expected = set(calendar.trading_days(sessions[0], sessions[-1]))
    missing = sorted(expected - set(sessions))
    for d in missing:
        sev = "warn" if calendar.is_verified(d) else "info"
        issues.append(QualityIssue("missing_session", sev, d, "no bar for expected trading session"))
    rets = df["close"].pct_change()
    known = known_action_dates or set()
    for d, r in zip(df["session_date"], rets, strict=True):
        if pd.notna(r) and abs(r) > extreme_move and d not in known:
            issues.append(QualityIssue("extreme_move", "warn", d,
                                       f"close-to-close move {r:+.1%} without a recorded corporate action"))
    return issues
