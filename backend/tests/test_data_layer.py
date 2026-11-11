from datetime import UTC, date, datetime, time
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import select, text

from market_sage.core.timeutil import IST, ist_datetime
from market_sage.data.adjust import adjust_bars
from market_sage.data.chunking import plan_chunks
from market_sage.data.models import CorporateAction, DataStatus, Interval
from market_sage.data.providers import angelone, nse_archive
from market_sage.data.providers.base import RateLimit
from market_sage.data.quality import check_daily_bars
from market_sage.data.ratelimit import RateLimiter
from market_sage.db import schema as s

FIX = Path(__file__).parent / "fixtures"


def test_parse_full_bhavcopy_with_delivery():
    df = nse_archive.parse_full_bhavcopy((FIX / "sample_sec_bhavdata_full.csv").read_bytes(), datetime.now(UTC), 1)
    assert list(df["symbol"]) == ["SAMPLEA", "SAMPLEB"]  # non-equity series dropped
    a = df.iloc[0]
    assert a["close"] == 104.0 and a["delivery_qty"] == 70000 and a["turnover"] == pytest.approx(153.45e5)
    assert a["session_date"] == date(2026, 11, 3)
    assert a["ts"] == ist_datetime(date(2026, 11, 3), time(9, 15))


def test_parse_udiff_bhavcopy():
    df = nse_archive.parse_udiff_bhavcopy((FIX / "sample_udiff_cm.csv").read_bytes(), datetime.now(UTC), None)
    assert list(df["symbol"]) == ["SAMPLEA", "SAMPLEB"]
    assert df.iloc[1]["isin"] == "INE000B01012" and df.iloc[1]["high"] == 2520.0


@pytest.mark.parametrize(
    "subject,expected",
    [
        ("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share", ("split", 5.0, 1.0, None)),
        ("Bonus 1:1", ("bonus", 1.0, 1.0, None)),
        ("Interim Dividend - Rs 5.50 Per Share", ("dividend", None, None, 5.5)),
        ("Annual General Meeting", ("other", None, None, None)),
    ],
)
def test_corporate_action_subject_parsing(subject, expected):
    assert nse_archive.parse_ca_subject(subject) == expected


def test_adjustment_split_and_bonus():
    sessions = [date(2026, 1, d) for d in (5, 6, 7, 8)]
    bars = pd.DataFrame(
        {
            "session_date": sessions,
            "open": [100.0, 100, 20, 20],
            "high": [100.0, 100, 20, 20],
            "low": [100.0, 100, 20, 20],
            "close": [100.0, 100, 20, 20],
            "volume": [10.0, 10, 50, 50],
            "delivery_qty": [5.0, 5, 25, 25],
        }
    )
    adj = adjust_bars(bars, [CorporateAction(1, date(2026, 1, 7), "split", 5, 1)])
    assert list(adj["close"]) == [20, 20, 20, 20] and list(adj["volume"]) == [50, 50, 50, 50]
    adj2 = adjust_bars(bars, [CorporateAction(1, date(2026, 1, 7), "bonus", 1, 1)])
    assert adj2["close"].iloc[0] == 50


def test_quality_checks_flag_problems(calendar):
    d = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 6), date(2026, 1, 9)]
    bars = pd.DataFrame(
        {
            "ts": range(4),
            "session_date": d,
            "open": [10.0, 10, 10, 10],
            "high": [11.0, 9, 11, 15],
            "low": [9.0, 9, 9, 9],
            "close": [10.0, 10, 10, 14],
            "volume": [100.0, 0, 100, -1],
        }
    )
    checks = {i.check for i in check_daily_bars(bars, calendar)}
    assert {
        "duplicate",
        "ohlc_inconsistent",
        "zero_volume",
        "negative_volume",
        "missing_session",
        "extreme_move",
    } <= checks


def test_chunk_planner_respects_window():
    a = datetime(2026, 1, 1, tzinfo=UTC)
    b = datetime(2026, 4, 1, tzinfo=UTC)
    chunks = plan_chunks(angelone.CAPABILITIES, Interval.M1, a, b)
    assert all((y - x).days <= 30 for x, y in chunks) and chunks[0][0] == a and chunks[-1][1] == b


def test_rate_limiter_waits():
    t = [0.0]
    slept = []
    rl = RateLimiter(
        RateLimit(per_second=2, per_minute=3),
        clock=lambda: t[0],
        sleep=lambda x: (slept.append(x), t.__setitem__(0, t[0] + x)),
    )
    for _ in range(4):
        rl.acquire()
    assert slept and sum(slept) >= 59  # 4th call must wait for the per-minute window


def test_angel_scrip_master_and_candles_and_ws_packet():
    recs = [
        {
            "token": "2885",
            "symbol": "RELIANCE-EQ",
            "name": "RELIANCE",
            "exch_seg": "NSE",
            "instrumenttype": "",
            "lotsize": "1",
            "tick_size": "10.000000",
        },
        {"token": "99999", "symbol": "NIFTY24DECFUT", "name": "NIFTY", "exch_seg": "NFO", "instrumenttype": "FUTIDX"},
        {"token": "500325", "symbol": "RELIANCE", "name": "RELIANCE", "exch_seg": "BSE", "instrumenttype": ""},
    ]
    insts = angelone.parse_scrip_master(recs)
    assert [(i.exchange, i.symbol, i.provider_token) for i in insts] == [
        ("NSE", "RELIANCE", "2885"),
        ("BSE", "RELIANCE", "500325"),
    ]
    assert insts[0].tick_size == 0.1
    df = angelone.parse_candles([["2026-11-03T09:15:00+05:30", 1, 2, 0.5, 1.5, 1000]], Interval.M5, datetime.now(UTC))
    assert df.iloc[0]["session_date"] == date(2026, 11, 3)
    assert df.iloc[0]["source_ts"] == datetime(2026, 11, 3, 9, 20, tzinfo=IST)
    ms = int(datetime(2026, 11, 3, 10, 0, tzinfo=IST).timestamp() * 1000)
    q = angelone.parse_ws_packet(angelone.build_ws_packet("2885", ms, 123450), datetime.now(UTC))
    assert q and q.ltp == 1234.5 and q.provider_token == "2885"
    pkt = angelone.build_ws_packet(
        "2885", ms, 123450, mode=angelone.WS_MODE_QUOTE, ohlc_paise=(120000, 125000, 119000, 121000), volume=777
    )
    q2 = angelone.parse_ws_packet(pkt, datetime.now(UTC))
    assert q2.high == 1250.0 and q2.prev_close == 1210.0 and q2.volume == 777


def test_angel_session_relogs_after_midnight(monkeypatch):
    calls = []

    class FakeHttp:
        def post(self, path, json, headers):
            calls.append(path)

            class R:
                status_code = 200

                def raise_for_status(self):
                    pass

                def json(self):
                    return {"status": True, "data": {"jwtToken": "j", "refreshToken": "r", "feedToken": "f"}}

            return R()

    now = [datetime(2026, 11, 3, 8, 0, tzinfo=IST)]
    sess = angelone.AngelSession("k", "C1", "0000", "JBSWY3DPEHPK3PXP", http=FakeHttp(), now=lambda: now[0])
    sess.ensure()
    sess.ensure()
    assert len(calls) == 1
    now[0] = datetime(2026, 11, 4, 0, 5, tzinfo=IST)
    sess.ensure()
    assert len(calls) == 2


def test_fixture_ingest_end_to_end(mds, market):
    rep_rows = mds.engine.connect().execute(select(s.ingestion_runs)).fetchall()
    assert rep_rows[0].status == "ok"
    inst = mds.instruments.by_symbol("NSE", market.split_symbol)
    raw = mds.daily_bars(inst["id"], adjusted=False)
    adj = mds.daily_bars(inst["id"], adjusted=True)
    i = raw.index[raw["session_date"] == market.split_ex_date][0]
    assert raw["close"].iloc[i] / raw["close"].iloc[i - 1] < 0.4  # raw shows the split drop
    assert 0.8 < adj["close"].iloc[i] / adj["close"].iloc[i - 1] < 1.25  # adjusted removes it
    # adjustment is point-in-time: before the ex-date the action is not applied
    pre = mds.daily_bars(
        inst["id"],
        until=market.split_ex_date.replace(day=1) if market.split_ex_date.day > 1 else market.split_ex_date,
        adjusted=True,
    )
    assert pre["adj_factor"].max() == 1.0
    with mds.engine.connect() as c:
        assert c.execute(select(s.raw_files.c.is_synthetic)).scalar() is True
        issues = c.execute(select(s.data_quality_issues.c.check)).scalars().all()
    assert "extreme_move" not in issues  # split was reconciled with the recorded corporate action


def test_bar_store_conflicts_keep_original(mds, market):
    inst = mds.instruments.by_symbol("NSE", "SYN001")
    bars = mds.bars.read("NSE", Interval.D1, inst["id"]).tail(2).copy()
    bars["close"] = bars["close"] * 1.01
    res = mds.bars.upsert("NSE", Interval.D1, inst["id"], bars)
    assert res.inserted == 0 and len(res.conflicts) == 2
    assert mds.bars.read("NSE", Interval.D1, inst["id"])["close"].iloc[-1] != bars["close"].iloc[-1]


def test_data_status_stale_vs_fresh(mds, market):
    iid = mds.instruments.by_symbol("NSE", "SYN001")["id"]
    fresh_now = datetime.combine(market.end, time(17, 0), tzinfo=IST)
    assert mds.data_status(iid, fresh_now) == DataStatus.SYNTHETIC
    later = datetime(market.end.year + 1, 1, 15, 17, 0, tzinfo=IST)
    assert mds.data_status(iid, later) == DataStatus.STALE


def test_raw_files_immutable(mds):
    with pytest.raises(Exception, match="append-only"):
        with mds.engine.begin() as c:
            c.execute(text("UPDATE raw_files SET sha256='x'"))


def test_parse_index_closes():
    df = nse_archive.parse_index_closes((FIX / "sample_ind_close_all.csv").read_bytes(), datetime.now(UTC), None)
    assert list(df["symbol"]) == ["NIFTY 50", "NIFTY BANK", "SOME CLOSE-ONLY INDEX"]  # duplicates dropped
    last = df.iloc[-1]
    assert last["open"] == last["high"] == last["low"] == last["close"] == 500
    assert df.iloc[0]["session_date"] == date(2026, 11, 3)


def test_liquid_universe_excludes_instruments_that_stopped_trading(mds, market):
    """A renamed/delisted symbol must not keep its last liquidity forever (PIT universe)."""
    assert len(mds.liquid_universe(market.end, 5)) == 5
    later = mds.calendar.add_sessions(market.end, 61)  # the whole 60-session window is after the last bar
    assert mds.liquid_universe(later, 5) == []
