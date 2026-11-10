"""MarketDataService: the only entry point analytical engines use for market data.

Routes data roles to providers, ingests into the warehouse (L0 raw, L1 canonical Parquet), runs
quality checks, records provenance and serves adjusted (L2) research series.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, and_, insert, select

from market_sage.core.calendar import ExchangeCalendar
from market_sage.core.timeutil import ist_datetime, utcnow
from market_sage.data import storage
from market_sage.data.adjust import adjust_bars
from market_sage.data.models import BAR_COLUMNS, CorporateAction, DataStatus, Interval, Quote
from market_sage.data.providers import nse_archive
from market_sage.data.providers.fixture import SyntheticMarket
from market_sage.data.quality import check_daily_bars
from market_sage.db import schema as s


@dataclass
class IngestReport:
    provider: str
    dataset: str
    run_id: int
    sessions: int = 0
    rows: int = 0
    instruments: int = 0
    issues: int = 0
    missing_files: list[date] = field(default_factory=list)
    status: str = "ok"
    message: str = ""


class MarketDataService:
    def __init__(self, engine: Engine, data_dir: Path, calendar: ExchangeCalendar | None = None) -> None:
        self.engine = engine
        self.data_dir = data_dir
        self.calendar = calendar or ExchangeCalendar.load()
        self.raw = storage.RawStore(engine, data_dir)
        self.bars = storage.BarStore(data_dir)
        self.instruments = storage.InstrumentRegistry(engine)
        self._latest_quotes: dict[int, Quote] = {}
        self._load_calendar_days()

    # --- calendar ----------------------------------------------------------------------------
    def _load_calendar_days(self) -> None:
        with self.engine.connect() as conn:
            for r in conn.execute(select(s.calendar_days).where(s.calendar_days.c.status == "holiday")):
                self.calendar.add_inferred_holiday(r.trade_date, r.source)

    def _record_calendar_day(self, d: date, status: str, source: str) -> None:
        with self.engine.begin() as conn:
            exists = conn.execute(select(s.calendar_days.c.trade_date).where(
                and_(s.calendar_days.c.trade_date == d, s.calendar_days.c.exchange == "NSE"))).first()
            if exists is None:
                conn.execute(insert(s.calendar_days).values(trade_date=d, exchange="NSE", status=status,
                                                            source=source))
        if status == "holiday":
            self.calendar.add_inferred_holiday(d, source)

    # --- run bookkeeping ---------------------------------------------------------------------
    def _start_run(self, provider: str, dataset: str) -> int:
        with self.engine.begin() as conn:
            res = conn.execute(insert(s.ingestion_runs).values(provider=provider, dataset=dataset,
                                                                started_at=utcnow(), status="running"))
            return int(res.inserted_primary_key[0])  # type: ignore[index]

    def _finish_run(self, rep: IngestReport) -> None:
        with self.engine.begin() as conn:
            conn.execute(s.ingestion_runs.update().where(s.ingestion_runs.c.id == rep.run_id).values(
                finished_at=utcnow(), status=rep.status, rows=rep.rows, message=rep.message[:2000]))

    def _record_issues(self, run_id: int, instrument_id: int, issues: list) -> int:
        if not issues:
            return 0
        now = utcnow()
        with self.engine.begin() as conn:
            conn.execute(insert(s.data_quality_issues), [
                {"run_id": run_id, "instrument_id": instrument_id, "dataset": "bars_1d", "trade_date": i.trade_date,
                 "check": i.check, "severity": i.severity, "detail": i.detail, "detected_at": now}
                for i in issues])
        return len(issues)

    # --- corporate actions -------------------------------------------------------------------
    def add_corporate_action(self, instrument_id: int, ca: CorporateAction, raw_file_id: int | None = None,
                             published_at: datetime | None = None) -> None:
        t = s.corporate_actions
        with self.engine.begin() as conn:
            exists = conn.execute(select(t.c.id).where(and_(t.c.instrument_id == instrument_id,
                                                            t.c.ex_date == ca.ex_date, t.c.kind == ca.kind))).first()
            if exists is None:
                conn.execute(insert(t).values(instrument_id=instrument_id, ex_date=ca.ex_date, kind=ca.kind,
                                              ratio_num=ca.ratio_num, ratio_den=ca.ratio_den,
                                              cash_amount=ca.cash_amount, purpose=ca.purpose, source=ca.source,
                                              published_at=published_at, raw_file_id=raw_file_id))

    def corporate_actions(self, instrument_id: int, known_by: datetime | None = None) -> list[CorporateAction]:
        """Corporate actions; with ``known_by``, only those published by then (PIT), when known."""
        t = s.corporate_actions
        q = select(t).where(t.c.instrument_id == instrument_id)
        with self.engine.connect() as conn:
            rows = conn.execute(q).fetchall()
        out = []
        for r in rows:
            if known_by is not None and r.published_at is not None and r.published_at > known_by:
                continue
            out.append(CorporateAction(instrument_id, r.ex_date, r.kind, r.ratio_num, r.ratio_den, r.cash_amount,
                                       r.purpose or "", r.source))
        return out

    # --- ingestion: synthetic fixture -----------------------------------------------------------
    def ingest_fixture(self, market: SyntheticMarket) -> IngestReport:
        run = self._start_run("fixture", "eod_bars")
        rep = IngestReport("fixture", "eod_bars", run)
        raw_id = self.raw.save("fixture", "synthetic_market", f"fixture://seed={market.seed}",
                               json.dumps({"seed": market.seed, "start": str(market.start), "end": str(market.end),
                                           "stocks": len(market.stocks)}).encode(),
                               "synthetic_market.json", is_synthetic=True,
                               licence_note="SYNTHETIC — not market data")
        start = ist_datetime(market.start, time(0, 0))
        end = ist_datetime(market.end + timedelta(days=1), time(0, 0))
        for inst in market.list_instruments():
            iid = self.instruments.get_or_create(inst.exchange, inst.symbol, isin=inst.isin, name=inst.name,
                                                 series=inst.series, sector=market.sector_of(inst.symbol),
                                                 is_index=inst.instrument_type == "INDEX")
            self.instruments.map_provider(inst, iid, market.start)
            bars = market.fetch_bars(inst, Interval.D1, start, end)
            bars["raw_file_id"] = raw_id
            res = self.bars.upsert(inst.exchange, Interval.D1, iid, bars)
            rep.rows += res.inserted
            rep.instruments += 1
        for symbol, ca in market.corporate_actions():
            iid = self.instruments.get_or_create("NSE", symbol)
            self.add_corporate_action(iid, ca, raw_id)
        for inst in market.list_instruments():
            iid = self.instruments.get_or_create(inst.exchange, inst.symbol)
            known = {c.ex_date for c in self.corporate_actions(iid)}
            rep.issues += self._record_issues(run, iid, check_daily_bars(
                self.bars.read(inst.exchange, Interval.D1, iid), self.calendar, known))
        rep.sessions = len(market.calendar.trading_days(market.start, market.end))
        rep.message = "SYNTHETIC fixture data ingested (not market data)"
        self._finish_run(rep)
        return rep

    # --- ingestion: NSE official archives ---------------------------------------------------
    def ingest_nse_eod(self, start: date, end: date, client: nse_archive.NseArchiveClient | None = None
                       ) -> IngestReport:
        """Ingest NSE full bhavcopy (OHLCV + delivery) for each weekday; a 404 on a weekday is recorded
        as an inferred holiday (history only)."""
        client = client or nse_archive.NseArchiveClient()
        run = self._start_run(nse_archive.PROVIDER, "sec_bhavdata_full")
        rep = IngestReport(nse_archive.PROVIDER, "sec_bhavdata_full", run)
        touched: set[int] = set()
        d = start
        try:
            while d <= end:
                if d.weekday() < 5:
                    url = nse_archive.full_bhavcopy_url(d)
                    content = client.get(url)
                    if content is None:
                        rep.missing_files.append(d)
                        if d < utcnow().date():
                            self._record_calendar_day(d, "holiday", "inferred: no NSE bhavcopy (404)")
                    else:
                        raw_id = self.raw.save(nse_archive.PROVIDER, "sec_bhavdata_full", url, content,
                                               f"sec_bhavdata_full_{d:%d%m%Y}.csv",
                                               licence_note=nse_archive.LICENCE_NOTE)
                        frame = nse_archive.parse_full_bhavcopy(content, utcnow(), raw_id)
                        touched |= self._store_eod_frame(frame)
                        rep.rows += len(frame)
                        rep.sessions += 1
                        self._record_calendar_day(d, "trading", "NSE bhavcopy present")
                d += timedelta(days=1)
        except Exception as exc:  # noqa: BLE001 - recorded, then surfaced
            rep.status, rep.message = "failed", f"{type(exc).__name__}: {exc}"
            self._finish_run(rep)
            raise
        for iid in touched:
            known = {c.ex_date for c in self.corporate_actions(iid)}
            rep.issues += self._record_issues(run, iid, check_daily_bars(
                self.bars.read("NSE", Interval.D1, iid), self.calendar, known))
        rep.instruments = len(touched)
        self._finish_run(rep)
        return rep

    def _store_eod_frame(self, frame: pd.DataFrame) -> set[int]:
        touched = set()
        for sym, g in frame.groupby("symbol"):
            first = g.iloc[0]
            iid = self.instruments.get_or_create("NSE", str(sym), isin=first.get("isin") or None,
                                                 name=first.get("name"), series=first.get("series"))
            self.bars.upsert("NSE", Interval.D1, iid, g[BAR_COLUMNS])
            touched.add(iid)
        return touched

    # --- serving ------------------------------------------------------------------------------
    def daily_bars(self, instrument_id: int, *, until: date | None = None, adjusted: bool = True,
                   known_by: datetime | None = None) -> pd.DataFrame:
        """Daily bars up to and including session ``until``. Adjusted with corporate actions whose
        ex-date is on/before ``until`` (an action after the cutoff cannot be known at the cutoff)."""
        inst = self.instruments.get(instrument_id)
        if inst is None:
            raise KeyError(instrument_id)
        df = self.bars.read(inst["exchange"], Interval.D1, instrument_id)
        if until is not None:
            df = df[df["session_date"] <= until]
        df = df.sort_values("ts").reset_index(drop=True)
        if adjusted:
            actions = [a for a in self.corporate_actions(instrument_id, known_by)
                       if until is None or a.ex_date <= until]
            df = adjust_bars(df, actions)
        return df

    def latest_session(self, instrument_id: int) -> date | None:
        inst = self.instruments.get(instrument_id)
        if inst is None:
            return None
        df = self.bars.read(inst["exchange"], Interval.D1, instrument_id)
        return None if df.empty else max(df["session_date"])

    def data_status(self, instrument_id: int, now: datetime) -> DataStatus:
        """EOD freshness: stale if the latest completed session's bar is missing (or ambiguous)."""
        inst = self.instruments.get(instrument_id)
        if inst is None:
            return DataStatus.STALE
        df = self.bars.read(inst["exchange"], Interval.D1, instrument_id)
        if df.empty:
            return DataStatus.STALE
        latest = max(df["session_date"])
        expected = self.calendar.latest_completed_session(now)
        if latest < expected:
            return DataStatus.STALE
        return DataStatus.SYNTHETIC if (df["provider"] == "fixture").any() else DataStatus.EOD

    # --- live quotes -------------------------------------------------------------------------
    def record_quote(self, q: Quote) -> None:
        self._latest_quotes[q.instrument_id] = q

    def latest_quote(self, instrument_id: int) -> Quote | None:
        return self._latest_quotes.get(instrument_id)
