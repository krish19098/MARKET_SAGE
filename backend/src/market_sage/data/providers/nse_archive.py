"""NSE official archives adapter: EOD bhavcopy (UDiFF), full bhavcopy with delivery, equity list,
corporate actions.

Source of record for daily OHLCV, delivery quantity and corporate actions (decision D1).
URL patterns and column layouts are based on NSE's published formats and **must be verified against
live files** before ``capabilities.verified`` is set (blocked in the development cloud environment).
Use is personal/non-commercial under the NSE Data Usage Policy; data is not redistributed.
"""

from __future__ import annotations

import io
import re
import time as _time
import zipfile
from datetime import date, datetime, time
from typing import Any

import httpx
import pandas as pd

from market_sage.core.timeutil import IST, ist_datetime, utcnow
from market_sage.data.models import BAR_COLUMNS, CorporateAction, DataRole, Interval
from market_sage.data.providers.base import ProviderCapabilities, RateLimit

PROVIDER = "nse_archive"
ARCHIVE = "https://nsearchives.nseindia.com"
WWW = "https://www.nseindia.com"
EQUITY_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}
LICENCE_NOTE = "NSE archive file; personal non-commercial use under NSE Data Usage Policy; do not redistribute"

CAPABILITIES = ProviderCapabilities(
    provider=PROVIDER,
    roles=frozenset({DataRole.EOD_BARS, DataRole.DELIVERY, DataRole.CORPORATE_ACTIONS, DataRole.UNIVERSE}),
    exchanges=frozenset({"NSE"}),
    intervals=frozenset({Interval.D1}),
    max_days_per_request={Interval.D1: 1},  # one file per session
    rate_limits={"archive": RateLimit(per_second=0.5)},
    realtime=False,
    verified=False,
    notes="URL/format assumptions pending verification against live NSE archives.",
)


def udiff_bhavcopy_url(d: date) -> str:
    return f"{ARCHIVE}/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"


def full_bhavcopy_url(d: date) -> str:
    return f"{ARCHIVE}/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"


def equity_list_url() -> str:
    return f"{ARCHIVE}/content/equities/EQUITY_L.csv"


def corporate_actions_url(start: date, end: date) -> str:
    return f"{WWW}/api/corporates-corporateActions?index=equities&from_date={start:%d-%m-%Y}&to_date={end:%d-%m-%Y}"


def _daily_ts(d: date) -> tuple[datetime, datetime]:
    return ist_datetime(d, time(9, 15)), ist_datetime(d, time(15, 30))


def parse_udiff_bhavcopy(content: bytes, received_ts: datetime, raw_file_id: int | None) -> pd.DataFrame:
    """Parse the CM UDiFF bhavcopy (zip or csv). Returns canonical bars + symbol/isin/series columns."""
    if content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            content = zf.read(zf.namelist()[0])
    df = pd.read_csv(io.BytesIO(content), dtype=str).rename(columns=lambda c: c.strip())
    df = df[df["SctySrs"].str.strip().isin(EQUITY_SERIES)]
    sess = pd.to_datetime(df["TradDt"].str.strip()).dt.date
    out = pd.DataFrame(
        {
            "symbol": df["TckrSymb"].str.strip(),
            "isin": df["ISIN"].str.strip(),
            "series": df["SctySrs"].str.strip(),
            "name": df.get("FinInstrmNm", df["TckrSymb"]).str.strip(),
            "session_date": sess,
            "open": df["OpnPric"].astype(float),
            "high": df["HghPric"].astype(float),
            "low": df["LwPric"].astype(float),
            "close": df["ClsPric"].astype(float),
            "volume": df["TtlTradgVol"].astype(float),
            "turnover": df["TtlTrfVal"].astype(float),
            "trades": pd.to_numeric(df.get("TtlNbOfTxsExctd"), errors="coerce"),
            "prev_close": pd.to_numeric(df.get("PrvsClsgPric"), errors="coerce"),
        }
    )
    return _finish(out, received_ts, raw_file_id)


def parse_full_bhavcopy(content: bytes, received_ts: datetime, raw_file_id: int | None) -> pd.DataFrame:
    """Parse ``sec_bhavdata_full`` (has delivery quantity). Headers/values carry leading spaces."""
    df = pd.read_csv(io.BytesIO(content), dtype=str, skipinitialspace=True)
    df = df.rename(columns=lambda c: c.strip()).apply(lambda c: c.str.strip())
    df = df[df["SERIES"].isin(EQUITY_SERIES)]
    num = lambda c: pd.to_numeric(df[c].replace({"-": None, "": None}), errors="coerce")  # noqa: E731
    out = pd.DataFrame(
        {
            "symbol": df["SYMBOL"],
            "isin": None,
            "series": df["SERIES"],
            "name": df["SYMBOL"],
            "session_date": pd.to_datetime(df["DATE1"], format="%d-%b-%Y").dt.date,
            "open": num("OPEN_PRICE"),
            "high": num("HIGH_PRICE"),
            "low": num("LOW_PRICE"),
            "close": num("CLOSE_PRICE"),
            "volume": num("TTL_TRD_QNTY"),
            "turnover": num("TURNOVER_LACS") * 1e5,
            "trades": num("NO_OF_TRADES"),
            "delivery_qty": num("DELIV_QTY"),
            "prev_close": num("PREV_CLOSE"),
        }
    )
    return _finish(out, received_ts, raw_file_id)


def _finish(out: pd.DataFrame, received_ts: datetime, raw_file_id: int | None) -> pd.DataFrame:
    if "delivery_qty" not in out:
        out["delivery_qty"] = float("nan")
    ts_pairs = [_daily_ts(d) for d in out["session_date"]]
    out["ts"] = [a for a, _ in ts_pairs]
    out["source_ts"] = [b for _, b in ts_pairs]
    out["received_ts"] = received_ts
    out["provider"] = PROVIDER
    out["raw_file_id"] = raw_file_id
    return out.reset_index(drop=True)


def parse_equity_list(content: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(content), dtype=str).rename(columns=lambda c: c.strip())
    return pd.DataFrame(
        {
            "symbol": df["SYMBOL"].str.strip(),
            "name": df["NAME OF COMPANY"].str.strip(),
            "series": df["SERIES"].str.strip(),
            "isin": df["ISIN NUMBER"].str.strip(),
            "listed_on": pd.to_datetime(df["DATE OF LISTING"].str.strip(), format="%d-%b-%Y", errors="coerce").dt.date,
        }
    )


_SPLIT = re.compile(r"(?:split|sub-?division).*?(?:rs\.?|re\.?)\s*([\d.]+).*?(?:rs\.?|re\.?)\s*([\d.]+)", re.I)
_BONUS = re.compile(r"bonus\s*(\d+)\s*:\s*(\d+)", re.I)
_DIV = re.compile(r"dividend.*?(?:rs\.?|re\.?)\s*([\d.]+)", re.I)


def parse_ca_subject(subject: str) -> tuple[str, float | None, float | None, float | None]:
    """Classify an NSE corporate-action subject into (kind, ratio_num, ratio_den, cash)."""
    if m := _SPLIT.search(subject):
        old_fv, new_fv = float(m.group(1)), float(m.group(2))
        if new_fv > 0 and old_fv > new_fv:
            return "split", old_fv / new_fv, 1.0, None
    if m := _BONUS.search(subject):
        return "bonus", float(m.group(1)), float(m.group(2)), None
    if m := _DIV.search(subject):
        return "dividend", None, None, float(m.group(1))
    return "other", None, None, None


def parse_corporate_actions(records: list[dict[str, Any]]) -> list[tuple[str, CorporateAction]]:
    out = []
    for r in records:
        subject = str(r.get("subject", ""))
        kind, num, den, cash = parse_ca_subject(subject)
        try:
            ex = datetime.strptime(str(r.get("exDate", "")).strip(), "%d-%b-%Y").replace(tzinfo=IST).date()
        except ValueError:
            continue
        out.append(
            (
                str(r.get("symbol", "")).strip(),
                CorporateAction(0, ex, kind, num, den, cash, purpose=subject, source=PROVIDER),
            )
        )
    return out


class NseArchiveClient:
    """HTTP client with polite pacing, retries and NSE cookie bootstrap for the JSON API."""

    def __init__(self, timeout: float = 30.0, max_retries: int = 4) -> None:
        self.max_retries = max_retries
        self._http = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MarketSage/0.1 (personal research)",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        self._last = 0.0
        self._cookies_ready = False

    def _pace(self) -> None:
        gap = 1.0 / CAPABILITIES.rate_limits["archive"].per_second
        wait = self._last + gap - _time.monotonic()
        if wait > 0:
            _time.sleep(wait)
        self._last = _time.monotonic()

    def get(self, url: str, *, api: bool = False) -> bytes | None:
        """Return content, or None for 404 (no file — e.g. holiday). Raises after retries."""
        if api and not self._cookies_ready:
            self._pace()
            self._http.get(WWW)
            self._cookies_ready = True
        delay = 2.0
        for attempt in range(self.max_retries):
            self._pace()
            try:
                resp = self._http.get(url)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.content
            except (httpx.HTTPError, httpx.TransportError):
                if attempt == self.max_retries - 1:
                    raise
                _time.sleep(delay)
                delay *= 2
        return None

    def session_now(self) -> datetime:
        return utcnow().astimezone(IST)


__all__ = [
    "BAR_COLUMNS",
    "CAPABILITIES",
    "LICENCE_NOTE",
    "NseArchiveClient",
    "corporate_actions_url",
    "equity_list_url",
    "full_bhavcopy_url",
    "parse_corporate_actions",
    "parse_equity_list",
    "parse_full_bhavcopy",
    "parse_udiff_bhavcopy",
    "udiff_bhavcopy_url",
]
