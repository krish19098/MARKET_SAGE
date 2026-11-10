import re
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import insert, text

from market_sage.core.calendar import ExchangeCalendar
from market_sage.core.config import Settings
from market_sage.core.timeutil import IST, FixedClock, ensure_utc, ist_datetime, to_ist
from market_sage.db import schema as s

REPO = Path(__file__).resolve().parents[2]


def test_execution_mode_paper_only():
    assert Settings(execution_mode="paper").execution_mode == "paper"
    with pytest.raises(ValidationError):
        Settings(execution_mode="live")


def test_naive_datetimes_rejected_and_ist_conversion():
    with pytest.raises(ValueError):
        ensure_utc(datetime(2026, 1, 1))  # noqa: DTZ001
    dt = ist_datetime(date(2026, 11, 3), time(9, 15))
    assert dt.tzinfo == UTC and dt.hour == 3 and dt.minute == 45
    assert to_ist(dt).hour == 9
    clock = FixedClock(dt)
    assert clock.now() == dt


def test_calendar_sessions_and_verification(tmp_path):
    f = tmp_path / "h.csv"
    f.write_text("date,kind,note\n2026-01-01,verified_year,test circular\n2026-01-26,holiday,Test Day\n")
    cal = ExchangeCalendar.load(f)
    assert not cal.is_trading_day(date(2026, 1, 26))
    assert cal.is_verified(date(2026, 3, 2)) and not cal.is_verified(date(2027, 3, 1))
    assert cal.previous_trading_day(date(2026, 1, 27)) == date(2026, 1, 23)
    st = cal.session_state(datetime(2026, 1, 27, 10, 0, tzinfo=IST))
    assert st.phase == "open" and st.trading_day
    assert cal.session_state(datetime(2026, 1, 27, 9, 5, tzinfo=IST)).phase == "pre_open"
    assert cal.latest_completed_session(datetime(2026, 1, 27, 11, 0, tzinfo=IST)) == date(2026, 1, 23)
    assert cal.latest_completed_session(datetime(2026, 1, 27, 16, 0, tzinfo=IST)) == date(2026, 1, 27)


def test_ledger_tables_are_append_only(engine):
    now = datetime.now(UTC)
    with engine.begin() as c:
        c.execute(insert(s.audit_log).values(ts=now, actor="test", action="x", detail={}))
    with pytest.raises(Exception, match="append-only"):
        with engine.begin() as c:
            c.execute(text("UPDATE audit_log SET actor='tamper'"))
    with pytest.raises(Exception, match="append-only"):
        with engine.begin() as c:
            c.execute(text("DELETE FROM audit_log"))


ORDER_PATTERNS = re.compile(
    r"place" r"Order|modify" r"Order|cancel" r"Order|/order/v1|gtt-" r"service|create" r"Rule", re.I)


def _source_files():
    for root in (REPO / "backend" / "src", REPO / "frontend" / "src"):
        if root.exists():
            yield from (p for p in root.rglob("*") if p.suffix in {".py", ".ts", ".tsx", ".js"})


def test_no_order_execution_endpoints_in_codebase():
    offenders = [str(p) for p in _source_files() if ORDER_PATTERNS.search(p.read_text(errors="ignore"))]
    assert offenders == [], f"order-execution references found: {offenders}"


SECRET_PATTERNS = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|eyJhbGciOi[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"
    r"|(?i:api[_-]?key|secret|password|totp)\s*[:=]\s*['\"][A-Za-z0-9/+_\-]{16,}['\"])")


def test_no_secrets_committed():
    roots = [REPO / "backend" / "src", REPO / "backend" / "tests", REPO / "frontend" / "src", REPO / "infra"]
    hits = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix not in {".png", ".ico", ".parquet", ".zip"}:
                if SECRET_PATTERNS.search(p.read_text(errors="ignore")):
                    hits.append(str(p))
    assert hits == []
    gi = (REPO / ".gitignore").read_text()
    assert ".env" in gi
