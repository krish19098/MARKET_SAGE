"""Angel One SmartAPI adapter — market data and read-only account access.

Scope (decision D1): live quotes (WebSocket 2.0 / REST polling fallback), intraday & daily candles,
instrument tokens, optional read-only holdings. **No order endpoints are implemented or referenced**;
MARKET SAGE is advisory + paper-trading only.

All limits below come from desk research with conflicting sources (see docs/DECISION_BRIEF_D1-D7.md).
Conservative values are used and ``capabilities.verified`` stays False until confirmed with live
documentation and test calls using the owner's credentials (M1 verification task).
"""

from __future__ import annotations

import asyncio
import json
import struct
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import httpx
import pandas as pd
import pyotp

from market_sage.core.timeutil import IST, ensure_utc, ist_datetime, utcnow
from market_sage.data.chunking import plan_chunks
from market_sage.data.models import (
    BAR_COLUMNS,
    DataRole,
    DataStatus,
    FeedStatus,
    Holding,
    Interval,
    ProviderInstrument,
    Quote,
)
from market_sage.data.providers.base import ProviderCapabilities, RateLimit
from market_sage.data.ratelimit import RateLimiter

PROVIDER = "angelone"
API_BASE = "https://apiconnect.angelone.in"
WS_URL = "wss://smartapisocket.angelone.in/smart-stream"
SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

INTERVAL_CODES = {
    Interval.M1: "ONE_MINUTE",
    Interval.M3: "THREE_MINUTE",
    Interval.M5: "FIVE_MINUTE",
    Interval.M10: "TEN_MINUTE",
    Interval.M15: "FIFTEEN_MINUTE",
    Interval.M30: "THIRTY_MINUTE",
    Interval.H1: "ONE_HOUR",
    Interval.D1: "ONE_DAY",
}
# WebSocket 2.0 exchange type codes.
WS_EXCHANGE_TYPES = {"NSE": 1, "NFO": 2, "BSE": 3, "BFO": 4, "MCX": 5}
WS_MODE_LTP, WS_MODE_QUOTE, WS_MODE_SNAP = 1, 2, 3

CAPABILITIES = ProviderCapabilities(
    provider=PROVIDER,
    roles=frozenset({DataRole.INTRADAY_BARS, DataRole.LIVE_QUOTES, DataRole.HOLDINGS, DataRole.EOD_BARS}),
    exchanges=frozenset({"NSE", "BSE"}),
    intervals=frozenset(INTERVAL_CODES),
    # Most conservative of the conflicting published per-request windows.
    max_days_per_request={
        Interval.M1: 30,
        Interval.M3: 60,
        Interval.M5: 90,
        Interval.M10: 90,
        Interval.M15: 200,
        Interval.M30: 200,
        Interval.H1: 400,
        Interval.D1: 2000,
    },
    earliest_date={Interval.M1: date(2016, 1, 1), Interval.D1: date(1990, 1, 1)},
    max_live_subscriptions_per_connection=1000,
    max_live_connections=3,
    rate_limits={
        "historical": RateLimit(per_second=2, per_minute=120, per_hour=5000),
        "quote": RateLimit(per_second=1),
        "default": RateLimit(per_second=5),
    },
    realtime=True,
    verified=False,
    notes="Scrip master verified live 2026-11-11 (163,238 records; 2,779 NSE equities parsed). REST/WS limits unverified "
          "(need owner credentials); session invalidated daily at midnight IST; static IP only needed for orders (not used).",
)


class AngelError(RuntimeError):
    pass


@dataclass
class AngelTokens:
    jwt: str
    refresh: str
    feed: str
    issued_on: date  # IST date; SmartAPI invalidates sessions at midnight


class AngelSession:
    """Login with client code + PIN + TOTP; re-login after the daily midnight invalidation."""

    def __init__(
        self,
        api_key: str,
        client_code: str,
        pin: str,
        totp_secret: str,
        http: httpx.Client | None = None,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self.api_key, self.client_code = api_key, client_code
        self._pin, self._totp = pin, totp_secret
        self._http = http or httpx.Client(base_url=API_BASE, timeout=20.0)
        self._now = now
        self.tokens: AngelTokens | None = None

    def headers(self, auth: bool = True) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": self.api_key,
        }
        if auth:
            h["Authorization"] = f"Bearer {self.ensure().jwt}"
        return h

    def _ist_today(self) -> date:
        return ensure_utc(self._now()).astimezone(IST).date()

    def ensure(self) -> AngelTokens:
        if self.tokens is None or self.tokens.issued_on != self._ist_today():
            self.login()
        assert self.tokens is not None
        return self.tokens

    def login(self) -> AngelTokens:
        body = {"clientcode": self.client_code, "password": self._pin, "totp": pyotp.TOTP(self._totp).now()}
        data = _unwrap(
            self._http.post(
                "/rest/auth/angelbroking/user/v1/loginByPassword", json=body, headers=self.headers(auth=False)
            )
        )
        self.tokens = AngelTokens(data["jwtToken"], data["refreshToken"], data["feedToken"], self._ist_today())
        return self.tokens


def _unwrap(resp: httpx.Response) -> Any:
    if resp.status_code == 403:
        raise AngelError("SmartAPI access denied (rate limit exceeded or not permitted)")
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("status", False):
        raise AngelError(f"SmartAPI error {payload.get('errorcode')}: {payload.get('message')}")
    return payload.get("data")


def parse_scrip_master(
    records: list[dict[str, Any]], exchanges: Sequence[str] = ("NSE", "BSE")
) -> list[ProviderInstrument]:
    """Extract cash-equity instruments from OpenAPIScripMaster.json records."""
    out = []
    for r in records:
        seg = r.get("exch_seg")
        if seg not in exchanges:
            continue
        sym = str(r.get("symbol", ""))
        itype = str(r.get("instrumenttype", "") or "")
        if seg == "NSE" and not sym.endswith("-EQ") and itype != "AMXIDX":
            continue
        if seg == "BSE" and itype not in ("", "AMXIDX"):
            continue
        tick = r.get("tick_size")
        out.append(
            ProviderInstrument(
                provider=PROVIDER,
                provider_token=str(r["token"]),
                exchange=str(seg),
                symbol=sym.removesuffix("-EQ"),
                name=r.get("name"),
                instrument_type="INDEX" if itype == "AMXIDX" else "EQ",
                lot_size=int(float(r.get("lotsize") or 1)),
                tick_size=float(tick) / 100.0 if tick not in (None, "") else None,  # published in paise
            )
        )
    return out


def parse_candles(rows: list[list[Any]], interval: Interval, received_ts: datetime) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=BAR_COLUMNS)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    ts = pd.to_datetime(df["ts"], utc=True)
    df["ts"] = list(ts.dt.to_pydatetime())
    df["session_date"] = list(ts.dt.tz_convert(IST).dt.date)
    if interval == Interval.D1:
        df["source_ts"] = [ist_datetime(d, datetime.min.time().replace(hour=15, minute=30)) for d in df["session_date"]]
    else:
        minutes = {
            Interval.M1: 1,
            Interval.M3: 3,
            Interval.M5: 5,
            Interval.M10: 10,
            Interval.M15: 15,
            Interval.M30: 30,
            Interval.H1: 60,
        }[interval]
        df["source_ts"] = list((ts + pd.Timedelta(minutes=minutes)).dt.to_pydatetime())  # bar close time
    for c in ("delivery_qty", "turnover", "trades"):
        df[c] = float("nan")
    df["received_ts"] = received_ts
    df["provider"] = PROVIDER
    df["raw_file_id"] = None
    return df[BAR_COLUMNS]


class AngelOneProvider:
    """Implements InstrumentSource, HistoricalBarSource, AccountSource and LiveFeedSource."""

    capabilities = CAPABILITIES

    def __init__(
        self,
        session: AngelSession,
        http: httpx.Client | None = None,
        limiter_factory: Callable[[RateLimit], RateLimiter] = RateLimiter,
    ) -> None:
        self.session = session
        self._http = http or httpx.Client(base_url=API_BASE, timeout=30.0)
        self._limiters = {k: limiter_factory(v) for k, v in CAPABILITIES.rate_limits.items()}

    def list_instruments(self) -> Sequence[ProviderInstrument]:
        resp = httpx.get(SCRIP_MASTER_URL, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            raise AngelError("scrip master unavailable or empty")
        return parse_scrip_master(data)

    def fetch_bars(
        self, instrument: ProviderInstrument, interval: Interval, start: datetime, end: datetime
    ) -> pd.DataFrame:
        frames = []
        for a, b in plan_chunks(CAPABILITIES, interval, ensure_utc(start), ensure_utc(end)):
            self._limiters["historical"].acquire()
            body = {
                "exchange": instrument.exchange,
                "symboltoken": instrument.provider_token,
                "interval": INTERVAL_CODES[interval],
                "fromdate": a.astimezone(IST).strftime("%Y-%m-%d %H:%M"),
                "todate": b.astimezone(IST).strftime("%Y-%m-%d %H:%M"),
            }
            data = _unwrap(
                self._http.post(
                    "/rest/secure/angelbroking/historical/v1/getCandleData", json=body, headers=self.session.headers()
                )
            )
            frames.append(parse_candles(data or [], interval, utcnow()))
        if not frames:
            return pd.DataFrame(columns=BAR_COLUMNS)
        out = pd.concat(frames, ignore_index=True).drop_duplicates("ts")
        return out[(out["ts"] >= start) & (out["ts"] < end)].reset_index(drop=True)

    def quotes(self, instruments: Sequence[ProviderInstrument]) -> list[Quote]:
        """REST polling fallback (FULL mode), batched conservatively at 50 tokens per request."""
        out: list[Quote] = []
        for i in range(0, len(instruments), 50):
            batch = instruments[i : i + 50]
            tokens: dict[str, list[str]] = {}
            for inst in batch:
                tokens.setdefault(inst.exchange, []).append(inst.provider_token)
            self._limiters["quote"].acquire()
            data = _unwrap(
                self._http.post(
                    "/rest/secure/angelbroking/market/v1/quote/",
                    json={"mode": "FULL", "exchangeTokens": tokens},
                    headers=self.session.headers(),
                )
            )
            received = utcnow()
            for q in (data or {}).get("fetched", []):
                feed_time = q.get("exchFeedTime")
                src = datetime.strptime(feed_time, "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST) if feed_time else received
                out.append(
                    Quote(
                        0,
                        float(q["ltp"]),
                        ensure_utc(src),
                        received,
                        PROVIDER,
                        open=q.get("open"),
                        high=q.get("high"),
                        low=q.get("low"),
                        prev_close=q.get("close"),
                        volume=q.get("tradeVolume"),
                        status=DataStatus.LIVE,
                        provider_token=str(q.get("symbolToken")),
                    )
                )
        return out

    def holdings(self) -> Sequence[Holding]:
        self._limiters["default"].acquire()
        data = _unwrap(
            self._http.get("/rest/secure/angelbroking/portfolio/v1/getHolding", headers=self.session.headers())
        )
        out = []
        for h in data or []:
            if not h.get("tradingsymbol"):
                continue  # reported data defect: holdings with null symbol are skipped, not guessed
            out.append(
                Holding(
                    None,
                    h.get("exchange", "NSE"),
                    str(h["tradingsymbol"]).removesuffix("-EQ"),
                    int(h.get("quantity", 0)),
                    float(h.get("averageprice", 0.0)),
                    PROVIDER,
                    raw=h,
                )
            )
        return out

    async def stream(
        self, instruments: Sequence[ProviderInstrument], mode: int = WS_MODE_QUOTE
    ) -> AsyncIterator[Quote | FeedStatus]:
        """WebSocket 2.0 stream with heartbeat; yields FeedStatus on connect/disconnect."""
        import websockets

        if len(instruments) > CAPABILITIES.max_live_subscriptions_per_connection:
            raise AngelError("subscription exceeds per-connection token limit")
        tokens = self.session.ensure()
        headers = {
            "Authorization": f"Bearer {tokens.jwt}",
            "x-api-key": self.session.api_key,
            "x-client-code": self.session.client_code,
            "x-feed-token": tokens.feed,
        }
        token_list: dict[int, list[str]] = {}
        for inst in instruments:
            token_list.setdefault(WS_EXCHANGE_TYPES[inst.exchange], []).append(inst.provider_token)
        sub = {
            "correlationID": "marketsage01",
            "action": 1,
            "params": {"mode": mode, "tokenList": [{"exchangeType": k, "tokens": v} for k, v in token_list.items()]},
        }
        async with websockets.connect(WS_URL, additional_headers=headers, ping_interval=None) as ws:
            yield FeedStatus(PROVIDER, True, utcnow(), message="connected")
            await ws.send(json.dumps(sub))

            async def heartbeat() -> None:
                while True:
                    await asyncio.sleep(25)
                    await ws.send("ping")

            hb = asyncio.create_task(heartbeat())
            try:
                async for msg in ws:
                    if isinstance(msg, bytes):
                        q = parse_ws_packet(msg, utcnow())
                        if q is not None:
                            yield q
            finally:
                hb.cancel()
                yield FeedStatus(PROVIDER, False, utcnow(), message="disconnected")


def parse_ws_packet(buf: bytes, received_ts: datetime) -> Quote | None:
    """Decode a WebSocket 2.0 binary tick (little-endian; prices in paise).

    Layout (per SmartAPI WS 2.0 spec as researched; verify in M1):
      0 mode(u8) | 1 exchange type(u8) | 2-26 token (25 bytes, NUL padded) | 27 seq(i64)
      | 35 exchange ts ms(i64) | 43 LTP(i64)  — LTP mode ends at 51
      Quote mode adds: 51 last qty | 59 avg price | 67 volume | 75 total buy qty(f64)
      | 83 total sell qty(f64) | 91 open | 99 high | 107 low | 115 close  (ends at 123)
    """
    if len(buf) < 51:
        return None
    mode = buf[0]
    token = buf[2:27].split(b"\x00", 1)[0].decode("ascii", "ignore")
    exch_ms, ltp = struct.unpack_from("<qq", buf, 35)
    src = datetime.fromtimestamp(exch_ms / 1000.0, tz=IST)
    kwargs: dict[str, Any] = {}
    if mode >= WS_MODE_QUOTE and len(buf) >= 123:
        _lq, _avg, vol = struct.unpack_from("<qqq", buf, 51)
        o, h, lo, c = struct.unpack_from("<qqqq", buf, 91)
        kwargs = {"open": o / 100, "high": h / 100, "low": lo / 100, "prev_close": c / 100, "volume": float(vol)}
    return Quote(
        0, ltp / 100.0, ensure_utc(src), received_ts, PROVIDER, status=DataStatus.LIVE, provider_token=token, **kwargs
    )


def build_ws_packet(
    token: str,
    exch_ms: int,
    ltp_paise: int,
    mode: int = WS_MODE_LTP,
    exchange_type: int = 1,
    ohlc_paise: tuple[int, int, int, int] = (0, 0, 0, 0),
    volume: int = 0,
) -> bytes:
    """Test helper: encode a packet in the layout parse_ws_packet expects (SYNTHETIC, for tests)."""
    head = struct.pack("<BB25sqqq", mode, exchange_type, token.encode().ljust(25, b"\x00"), 1, exch_ms, ltp_paise)
    if mode == WS_MODE_LTP:
        return head
    return head + struct.pack("<qqqddqqqq", 0, 0, volume, 0.0, 0.0, *ohlc_paise)
