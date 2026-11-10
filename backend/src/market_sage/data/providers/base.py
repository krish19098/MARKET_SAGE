"""Broker-independent provider protocols and capability declarations.

Capabilities are *data*: limits live in one place and drive chunk planning and rate limiting.
Adding a provider (DhanHQ, Kite, Upstox, a licensed vendor) means implementing these protocols and
declaring capabilities — analytical engines do not change.

There is intentionally **no order-execution protocol** here: MARKET SAGE is advisory/paper-only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, runtime_checkable

import pandas as pd

from market_sage.data.models import DataRole, FeedStatus, Holding, Interval, ProviderInstrument, Quote


@dataclass(frozen=True)
class RateLimit:
    per_second: float
    per_minute: int | None = None
    per_hour: int | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    roles: frozenset[DataRole]
    exchanges: frozenset[str]
    intervals: frozenset[Interval] = frozenset()
    max_days_per_request: dict[Interval, int] = field(default_factory=dict)
    earliest_date: dict[Interval, date] = field(default_factory=dict)
    max_live_subscriptions_per_connection: int = 0
    max_live_connections: int = 0
    rate_limits: dict[str, RateLimit] = field(default_factory=dict)
    realtime: bool = False
    verified: bool = False  # True only once limits were confirmed against live docs AND test calls
    notes: str = ""


@runtime_checkable
class InstrumentSource(Protocol):
    capabilities: ProviderCapabilities

    def list_instruments(self) -> Sequence[ProviderInstrument]: ...


@runtime_checkable
class HistoricalBarSource(Protocol):
    capabilities: ProviderCapabilities

    def fetch_bars(
        self, instrument: ProviderInstrument, interval: Interval, start: datetime, end: datetime
    ) -> pd.DataFrame:
        """Return canonical bar columns (without ``instrument_id``), unadjusted."""
        ...


@runtime_checkable
class LiveFeedSource(Protocol):
    capabilities: ProviderCapabilities

    def stream(self, instruments: Sequence[ProviderInstrument]) -> AsyncIterator[Quote | FeedStatus]: ...


@runtime_checkable
class AccountSource(Protocol):
    """Read-only account access (holdings/positions). No order methods exist by design."""

    capabilities: ProviderCapabilities

    def holdings(self) -> Sequence[Holding]: ...
