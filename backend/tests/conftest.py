"""Test fixtures. SQLite by default; set MARKET_SAGE_TEST_DATABASE_URL to a PostgreSQL URL to run the
whole suite against PostgreSQL (each test gets a fresh database cloned from a migrated template)."""

from __future__ import annotations

import os
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from market_sage.core.calendar import ExchangeCalendar
from market_sage.db.engine import make_engine, upgrade_to_head

PG_URL = os.environ.get("MARKET_SAGE_TEST_DATABASE_URL")
FIXTURE_END = date(2026, 10, 30)  # fixed so synthetic data is deterministic across runs


@pytest.fixture(scope="session")
def _pg_template():
    if not PG_URL:
        yield None
        return
    base, _, _ = PG_URL.rpartition("/")
    admin = create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
    tmpl = f"ms_tmpl_{uuid.uuid4().hex[:8]}"
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {tmpl}"))
    upgrade_to_head(f"{base}/{tmpl}")
    yield admin, base, tmpl
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {tmpl} WITH (FORCE)"))


@pytest.fixture
def db_url(tmp_path: Path, _pg_template):
    if _pg_template is None:
        url = f"sqlite:///{tmp_path}/test.db"
        upgrade_to_head(url)
        yield url
        return
    admin, base, tmpl = _pg_template
    name = f"ms_t_{uuid.uuid4().hex[:10]}"
    with admin.connect() as c:
        c.execute(text(f"CREATE DATABASE {name} TEMPLATE {tmpl}"))
    yield f"{base}/{name}"
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))


@pytest.fixture
def engine(db_url):
    eng = make_engine(db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def calendar() -> ExchangeCalendar:
    return ExchangeCalendar()


@pytest.fixture
def market(calendar):
    from market_sage.data.providers.fixture import SyntheticMarket

    return SyntheticMarket(calendar, date(2021, 1, 1), FIXTURE_END, n_stocks=12, seed=11)


@pytest.fixture
def mds(engine, tmp_path, calendar, market):
    from market_sage.data.service import MarketDataService

    svc = MarketDataService(engine, tmp_path / "data", calendar)
    svc.ingest_fixture(market)
    return svc
