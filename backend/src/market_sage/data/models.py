"""Canonical, provider-independent market data objects.

Analytical engines only ever see these types (keyed by internal ``instrument_id``), never broker payloads.
Bar frames use the columns in ``BAR_COLUMNS``; timestamps are aware UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class Interval(StrEnum):
    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M10 = "10m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    D1 = "1d"


class DataStatus(StrEnum):
    LIVE = "live"
    DELAYED = "delayed"
    EOD = "eod"
    STALE = "stale"
    SYNTHETIC = "synthetic"
    HISTORICAL = "historical"


class DataRole(StrEnum):
    EOD_BARS = "eod_bars"
    DELIVERY = "delivery"
    CORPORATE_ACTIONS = "corporate_actions"
    UNIVERSE = "universe"
    INTRADAY_BARS = "intraday_bars"
    LIVE_QUOTES = "live_quotes"
    HOLDINGS = "holdings"
    FUNDAMENTALS = "fundamentals"


# Canonical bar frame columns. ``ts`` = bar open time (UTC); for daily bars, 09:15 IST of the session.
BAR_COLUMNS = [
    "ts",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "delivery_qty",
    "turnover",
    "trades",
    "source_ts",
    "received_ts",
    "provider",
    "raw_file_id",
]


@dataclass(frozen=True)
class ProviderInstrument:
    provider: str
    provider_token: str
    exchange: str
    symbol: str
    name: str | None = None
    isin: str | None = None
    series: str | None = None
    instrument_type: str | None = None
    lot_size: int | None = None
    tick_size: float | None = None


@dataclass(frozen=True)
class Quote:
    instrument_id: int
    ltp: float
    source_ts: datetime
    received_ts: datetime
    provider: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: float | None = None
    status: DataStatus = DataStatus.LIVE
    provider_token: str = ""  # set by adapters; MarketDataService maps it to instrument_id


@dataclass(frozen=True)
class FeedStatus:
    provider: str
    connected: bool
    at: datetime
    last_tick_at: datetime | None = None
    latency_ms: float | None = None
    message: str = ""


@dataclass(frozen=True)
class CorporateAction:
    instrument_id: int
    ex_date: date
    kind: str
    ratio_num: float | None = None
    ratio_den: float | None = None
    cash_amount: float | None = None
    purpose: str = ""
    source: str = ""


@dataclass(frozen=True)
class Holding:
    instrument_id: int | None
    exchange: str
    symbol: str
    quantity: int
    avg_price: float
    provider: str
    raw: dict[str, object] = field(default_factory=dict)
