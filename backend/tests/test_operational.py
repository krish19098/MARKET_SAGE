"""Operational QA: ingestion with holidays/outages, restart recovery, timezone boundaries, migrations."""

from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from market_sage.core.calendar import ExchangeCalendar
from market_sage.core.timeutil import IST
from market_sage.data.service import MarketDataService
from market_sage.db import schema as s
from market_sage.db.engine import make_engine

FIX = Path(__file__).parent / "fixtures"


class FakeNse:
    """Serves the SAMPLE full-bhavcopy for 2026-11-03 only; other weekdays 404 (as on holidays)."""

    def __init__(self, fail: bool = False):
        self.fail, self.calls = fail, []

    def get(self, url, api=False):
        self.calls.append(url)
        if self.fail:
            raise httpx.ConnectError("provider unreachable")
        return (FIX / "sample_sec_bhavdata_full.csv").read_bytes() if "03112026" in url else None


def test_nse_ingestion_infers_holidays_and_is_idempotent(engine, tmp_path):
    mds = MarketDataService(engine, tmp_path / "d", ExchangeCalendar())
    rep = mds.ingest_nse_eod(date(2026, 11, 2), date(2026, 11, 4), client=FakeNse())
    assert rep.sessions == 1 and rep.rows == 2 and set(rep.missing_files) == {date(2026, 11, 2), date(2026, 11, 4)}
    assert not mds.calendar.is_trading_day(date(2026, 11, 2))  # inferred from missing official file
    iid = mds.instruments.by_symbol("NSE", "SAMPLEA")["id"]
    bars = mds.daily_bars(iid)
    assert bars["delivery_qty"].iloc[0] == 70000 and bars["provider"].iloc[0] == "nse_archive"
    rep2 = mds.ingest_nse_eod(date(2026, 11, 3), date(2026, 11, 3), client=FakeNse())
    assert len(mds.daily_bars(iid)) == 1 and rep2.rows == 2  # same raw file deduplicated, bars not duplicated
    with engine.connect() as c:
        assert c.execute(select(s.raw_files)).fetchall().__len__() == 1


def test_provider_outage_is_recorded_not_hidden(engine, tmp_path):
    mds = MarketDataService(engine, tmp_path / "d", ExchangeCalendar())
    with pytest.raises(httpx.ConnectError):
        mds.ingest_nse_eod(date(2026, 11, 3), date(2026, 11, 3), client=FakeNse(fail=True))
    with engine.connect() as c:
        run = c.execute(select(s.ingestion_runs)).fetchall()[-1]
    assert run.status == "failed" and "unreachable" in run.message


def test_restart_recovery_preserves_state(db_url, tmp_path, market):
    e1 = make_engine(db_url)
    m1 = MarketDataService(e1, tmp_path / "d", ExchangeCalendar())
    m1.ingest_fixture(market)
    n = len(m1.instruments.all())
    e1.dispose()
    e2 = make_engine(db_url)  # simulated process restart
    m2 = MarketDataService(e2, tmp_path / "d", ExchangeCalendar())
    assert len(m2.instruments.all()) == n
    iid = m2.instruments.by_symbol("NSE", "SYN001")["id"]
    assert not m2.daily_bars(iid).empty


def test_timezone_boundary_close():
    cal = ExchangeCalendar()
    before = datetime(2026, 11, 3, 15, 29, 59, tzinfo=IST)
    after = datetime(2026, 11, 3, 15, 30, 0, tzinfo=IST)
    assert cal.latest_completed_session(before) == date(2026, 11, 2)
    assert cal.latest_completed_session(after) == date(2026, 11, 3)
    # 23:30 UTC on Nov 3 is 05:00 IST on Nov 4: market closed, last completed session is Nov 3
    late_utc = datetime(2026, 11, 3, 23, 30, tzinfo=UTC)
    assert cal.session_state(late_utc).phase == "closed"
    assert cal.latest_completed_session(late_utc) == date(2026, 11, 3)
