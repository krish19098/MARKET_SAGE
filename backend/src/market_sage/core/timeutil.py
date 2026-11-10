"""Time handling: UTC internally, Asia/Kolkata for display and exchange-session logic.

A ``Clock`` abstraction lets backtests and tests replay time deterministically, which is the
basis of look-ahead-free evaluation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Return an aware UTC datetime; naive values are rejected to prevent silent timezone bugs."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed; attach a timezone")
    return dt.astimezone(UTC)


def to_ist(dt: datetime) -> datetime:
    return ensure_utc(dt).astimezone(IST)


def ist_iso(dt: datetime | None) -> str | None:
    return to_ist(dt).isoformat() if dt is not None else None


def ist_datetime(d: date, t: time) -> datetime:
    """Build an aware datetime for a wall-clock IST date/time and return it in UTC."""
    return datetime.combine(d, t, tzinfo=IST).astimezone(UTC)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return utcnow()


class FixedClock:
    """Deterministic clock for tests and historical replay."""

    def __init__(self, at: datetime) -> None:
        self._at = ensure_utc(at)

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = ensure_utc(at)
