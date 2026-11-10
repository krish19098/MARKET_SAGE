"""Deterministic SYNTHETIC market for development and tests.

Everything produced here is labelled synthetic (provider ``fixture``, ``raw_files.is_synthetic``,
data status ``synthetic``). It must never be presented as market data or used as market validation.

The generator has a market factor with regime switching, sector factors, idiosyncratic noise,
volume/delivery dynamics and one split so that adjustment and quality logic are exercised.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import numpy as np
import pandas as pd

from market_sage.core.calendar import ExchangeCalendar
from market_sage.core.timeutil import ist_datetime, utcnow
from market_sage.data.models import (
    BAR_COLUMNS,
    CorporateAction,
    DataRole,
    DataStatus,
    FeedStatus,
    Interval,
    ProviderInstrument,
    Quote,
)
from market_sage.data.providers.base import ProviderCapabilities

PROVIDER = "fixture"
INDEX_SYMBOL = "SYNNIFTY"
SECTORS = ["SYN-BANK", "SYN-IT", "SYN-AUTO", "SYN-PHARMA", "SYN-ENERGY"]
REGIME_DRIFT = {"bull": 0.0008, "bear": -0.0009, "sideways": 0.0}
REGIME_VOL = {"bull": 0.009, "bear": 0.016, "sideways": 0.008}


@dataclass(frozen=True)
class SyntheticStock:
    symbol: str
    sector: str
    base_price: float
    beta: float
    idio_vol: float


class SyntheticMarket:
    capabilities = ProviderCapabilities(
        provider=PROVIDER,
        roles=frozenset(
            {DataRole.EOD_BARS, DataRole.DELIVERY, DataRole.CORPORATE_ACTIONS, DataRole.UNIVERSE, DataRole.LIVE_QUOTES}
        ),
        exchanges=frozenset({"NSE"}),
        intervals=frozenset({Interval.D1}),
        max_days_per_request={Interval.D1: 100000},
        realtime=False,
        verified=True,
        notes="SYNTHETIC fixture data for development/testing only.",
    )

    def __init__(
        self,
        calendar: ExchangeCalendar,
        start: date,
        end: date,
        n_stocks: int = 30,
        seed: int = 7,
        planted_signal: float = 0.0,
    ) -> None:
        """``planted_signal`` > 0 adds a deliberately learnable momentum effect so the full pipeline
        (model skill, promotion gate, BUY path) can be exercised. Any edge found on such data is an
        artefact of the generator, never evidence about real markets."""
        self.calendar, self.start, self.end, self.seed = calendar, start, end, seed
        self.planted_signal = planted_signal
        rng = np.random.default_rng(seed)
        self.stocks = [
            SyntheticStock(
                f"SYN{i:03d}",
                SECTORS[i % len(SECTORS)],
                float(rng.uniform(80, 2500)),
                float(rng.uniform(0.6, 1.5)),
                float(rng.uniform(0.008, 0.022)),
            )
            for i in range(1, n_stocks + 1)
        ]
        self.split_symbol = self.stocks[2].symbol
        sessions = calendar.trading_days(start, end)
        self.split_ex_date = sessions[int(len(sessions) * 0.6)] if len(sessions) > 10 else None
        self._frames = self._generate(sessions, rng)

    # --- generation -----------------------------------------------------------------------
    def _generate(self, sessions: list[date], rng: np.random.Generator) -> dict[str, pd.DataFrame]:
        n = len(sessions)
        regimes, cur = [], "bull"
        trans = {"bull": [0.985, 0.005, 0.01], "bear": [0.01, 0.975, 0.015], "sideways": [0.015, 0.01, 0.975]}
        names = ["bull", "bear", "sideways"]
        for _ in range(n):
            regimes.append(cur)
            cur = names[int(rng.choice(3, p=trans[cur]))]
        self.regimes = pd.Series(regimes, index=sessions)
        mkt = np.array([rng.normal(REGIME_DRIFT[r], REGIME_VOL[r]) for r in regimes])
        sector_ret = {s: rng.normal(0, 0.006, n) + 0.3 * np.roll(rng.normal(0, 0.004, n), 1) for s in SECTORS}
        frames: dict[str, pd.DataFrame] = {}
        received = utcnow()
        for st in self.stocks:
            # mild short-term momentum in idiosyncratic returns (AR(1)) so setups have structure
            eps = rng.normal(0, st.idio_vol, n)
            idio = np.zeros(n)
            for t in range(1, n):
                planted = 0.0
                if self.planted_signal and t > 20:
                    z = idio[t - 20 : t].sum() / (st.idio_vol * np.sqrt(20))
                    planted = self.planted_signal * 0.0025 * np.tanh(z)
                idio[t] = 0.08 * idio[t - 1] + eps[t] + planted
            r = st.beta * mkt + sector_ret[st.sector] + idio
            close = st.base_price * np.exp(np.cumsum(r))
            frames[st.symbol] = self._ohlcv(st.symbol, sessions, close, r, rng, received)
        idx_close = 10000 * np.exp(np.cumsum(mkt))
        frames[INDEX_SYMBOL] = self._ohlcv(INDEX_SYMBOL, sessions, idx_close, mkt, rng, received, index=True)
        for sector in SECTORS:
            sec_close = 1000 * np.exp(np.cumsum(mkt + sector_ret[sector]))
            frames[sector] = self._ohlcv(
                sector, sessions, sec_close, mkt + sector_ret[sector], rng, received, index=True
            )
        if self.split_ex_date is not None:  # raw (unadjusted) prices drop 5x at the ex-date
            f = frames[self.split_symbol]
            post = f["session_date"] >= self.split_ex_date
            for c in ("open", "high", "low", "close"):
                f.loc[post, c] = f.loc[post, c] / 5.0
            f.loc[post, "volume"] = f.loc[post, "volume"] * 5
            f.loc[post, "delivery_qty"] = f.loc[post, "delivery_qty"] * 5
        return frames

    def _ohlcv(
        self,
        symbol: str,
        sessions: list[date],
        close: np.ndarray,
        r: np.ndarray,
        rng: np.random.Generator,
        received: datetime,
        index: bool = False,
    ) -> pd.DataFrame:
        n = len(sessions)
        prev = np.concatenate([[close[0] / np.exp(r[0])], close[:-1]])
        gap = rng.normal(0, 0.003, n)
        open_ = prev * np.exp(gap)
        span = np.abs(rng.normal(0, 0.008, n)) + np.abs(r) * 0.5
        high = np.maximum(open_, close) * (1 + span * rng.uniform(0.2, 1.0, n))
        low = np.minimum(open_, close) * (1 - span * rng.uniform(0.2, 1.0, n))
        base_vol = 0 if index else rng.uniform(2e5, 4e6)
        vol = base_vol * np.exp(rng.normal(0, 0.35, n)) * (1 + 25 * np.abs(r))
        deliv = vol * np.clip(rng.normal(0.45, 0.1, n), 0.1, 0.9)
        ts = [ist_datetime(d, time(9, 15)) for d in sessions]
        src = [ist_datetime(d, time(15, 30)) for d in sessions]
        return pd.DataFrame(
            {
                "ts": ts,
                "session_date": sessions,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": np.round(vol),
                "delivery_qty": np.round(deliv),
                "turnover": vol * close,
                "trades": np.round(vol / 50),
                "source_ts": src,
                "received_ts": received,
                "provider": PROVIDER,
                "raw_file_id": None,
            }
        )[BAR_COLUMNS]

    # --- provider protocols --------------------------------------------------------------------
    def list_instruments(self) -> Sequence[ProviderInstrument]:
        out = [
            ProviderInstrument(
                PROVIDER,
                s.symbol,
                "NSE",
                s.symbol,
                name=f"Synthetic {s.symbol}",
                isin=f"INSYN{s.symbol[3:]}0000"[:12],
                series="EQ",
                instrument_type="EQ",
            )
            for s in self.stocks
        ]
        for sym in [INDEX_SYMBOL, *SECTORS]:
            out.append(
                ProviderInstrument(PROVIDER, sym, "NSE", sym, name=f"Synthetic index {sym}", instrument_type="INDEX")
            )
        return out

    def sector_of(self, symbol: str) -> str | None:
        return next((s.sector for s in self.stocks if s.symbol == symbol), None)

    def fetch_bars(
        self, instrument: ProviderInstrument, interval: Interval, start: datetime, end: datetime
    ) -> pd.DataFrame:
        if interval != Interval.D1:
            raise ValueError("synthetic fixture provides daily bars only")
        f = self._frames[instrument.provider_token]
        return f[(f["ts"] >= start) & (f["ts"] < end)].reset_index(drop=True).copy()

    def corporate_actions(self) -> list[tuple[str, CorporateAction]]:
        if self.split_ex_date is None:
            return []
        return [
            (
                self.split_symbol,
                CorporateAction(
                    instrument_id=0,
                    ex_date=self.split_ex_date,
                    kind="split",
                    ratio_num=5,
                    ratio_den=1,
                    purpose="SYNTHETIC split 1:5",
                    source=PROVIDER,
                ),
            )
        ]

    async def stream(
        self, instruments: Sequence[ProviderInstrument], interval_s: float = 1.0, max_ticks: int | None = None
    ) -> AsyncIterator[Quote | FeedStatus]:
        """Simulated quotes around the last synthetic close (status=synthetic)."""
        rng = np.random.default_rng(self.seed + 1)
        last = {i.provider_token: float(self._frames[i.provider_token]["close"].iloc[-1]) for i in instruments}
        yield FeedStatus(PROVIDER, True, utcnow(), message="SYNTHETIC feed connected")
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            for inst in instruments:
                last[inst.provider_token] *= float(np.exp(rng.normal(0, 0.002)))
                now = utcnow()
                yield Quote(
                    instrument_id=0,
                    ltp=round(last[inst.provider_token], 2),
                    source_ts=now,
                    received_ts=now,
                    provider=PROVIDER,
                    status=DataStatus.SYNTHETIC,
                    provider_token=inst.provider_token,
                )
                ticks += 1
            await asyncio.sleep(interval_s)


def default_fixture(
    calendar: ExchangeCalendar | None = None, years: float = 6.0, n_stocks: int = 30, end: date | None = None
) -> SyntheticMarket:
    cal = calendar or ExchangeCalendar()
    end = end or datetime.now(UTC).date()
    start = end - timedelta(days=int(365 * years))
    return SyntheticMarket(cal, start, end, n_stocks=n_stocks)
