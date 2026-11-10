"""Exchange trading calendar for NSE/BSE cash equities.

Holidays are data, not code: they are loaded from ``data/calendar/holidays.csv`` (published exchange
circulars) and may also be *inferred for past dates* from the absence of an official bhavcopy.
For a date whose year has no verified holiday list, the calendar reports ``verified=False`` so the
decision layer can treat ambiguous gaps conservatively (suppression), as required by the spec.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

from market_sage.core.timeutil import IST, ensure_utc

PRE_OPEN_START = time(9, 0)
CONTINUOUS_START = time(9, 15)
CONTINUOUS_END = time(15, 30)
POST_CLOSE_END = time(16, 0)

DEFAULT_HOLIDAY_FILE = Path(__file__).resolve().parents[1] / "resources" / "calendar" / "holidays.csv"


@dataclass(frozen=True)
class SessionState:
    trading_day: bool
    phase: str  # closed | pre_open | open | post_close
    verified: bool  # False when the holiday list for this year is not verified


@dataclass
class ExchangeCalendar:
    holidays: dict[date, str] = field(default_factory=dict)
    verified_years: set[int] = field(default_factory=set)
    special_sessions: dict[date, tuple[time, time]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = DEFAULT_HOLIDAY_FILE) -> ExchangeCalendar:
        cal = cls()
        if not path.exists():
            return cal
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if not row.get("date") or row["date"].startswith("#"):
                    continue
                d = date.fromisoformat(row["date"])
                kind = (row.get("kind") or "holiday").strip()
                if kind == "verified_year":
                    cal.verified_years.add(d.year)
                elif kind == "special_session":
                    start, end = row["note"].split("-")
                    cal.special_sessions[d] = (time.fromisoformat(start), time.fromisoformat(end))
                else:
                    cal.holidays[d] = row.get("note", "")
        return cal

    def add_inferred_holiday(self, d: date, note: str = "inferred: no exchange bhavcopy") -> None:
        self.holidays.setdefault(d, note)

    def is_verified(self, d: date) -> bool:
        return d.year in self.verified_years

    def is_trading_day(self, d: date) -> bool:
        if d in self.special_sessions:
            return True
        return d.weekday() < 5 and d not in self.holidays

    def previous_trading_day(self, d: date) -> date:
        cur = d - timedelta(days=1)
        while not self.is_trading_day(cur):
            cur -= timedelta(days=1)
        return cur

    def next_trading_day(self, d: date) -> date:
        cur = d + timedelta(days=1)
        while not self.is_trading_day(cur):
            cur += timedelta(days=1)
        return cur

    def trading_days(self, start: date, end: date) -> list[date]:
        out, cur = [], start
        while cur <= end:
            if self.is_trading_day(cur):
                out.append(cur)
            cur += timedelta(days=1)
        return out

    def add_sessions(self, d: date, n: int) -> date:
        cur = d
        for _ in range(n):
            cur = self.next_trading_day(cur)
        return cur

    def session_state(self, at: datetime) -> SessionState:
        local = ensure_utc(at).astimezone(IST)
        d, t = local.date(), local.time()
        verified = self.is_verified(d)
        if not self.is_trading_day(d):
            return SessionState(False, "closed", verified)
        start, end = self.special_sessions.get(d, (CONTINUOUS_START, CONTINUOUS_END))
        if d in self.special_sessions:
            phase = "open" if start <= t < end else "closed"
        elif PRE_OPEN_START <= t < CONTINUOUS_START:
            phase = "pre_open"
        elif start <= t < end:
            phase = "open"
        elif end <= t < POST_CLOSE_END:
            phase = "post_close"
        else:
            phase = "closed"
        return SessionState(True, phase, verified)

    def latest_completed_session(self, at: datetime) -> date:
        """Most recent trading date whose regular session has fully closed at ``at``."""
        local = ensure_utc(at).astimezone(IST)
        d = local.date()
        if self.is_trading_day(d) and local.time() >= CONTINUOUS_END:
            return d
        return self.previous_trading_day(d)
