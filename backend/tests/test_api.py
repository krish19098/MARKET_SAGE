"""API: authentication, five-screen endpoints, positions (actual vs paper), invest, push subscription."""

from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from market_sage.api.app import create_app
from market_sage.api.auth import hash_password
from market_sage.container import Container
from market_sage.core.config import Settings
from market_sage.core.timeutil import IST
from market_sage.portfolio.risk import settings_for_mode


@pytest.fixture
def client(engine, mds, tmp_path):
    st = Settings(database_url=str(engine.url), data_dir=tmp_path / "data", auth_password_hash=SecretStr(hash_password("correct horse battery")),
                  jwt_secret=SecretStr("test-secret-test-secret-test-secret"))
    c = Container.build(st, engine)
    c.mds, c.store = mds, c.pipeline.store
    c.pipeline.mds = mds
    c.pipeline.store.mds = mds
    c.monitor.mds = mds
    cutoff = date(2026, 10, 30)
    c.pipeline.evaluate_universe(cutoff, datetime.combine(cutoff, time(18), tzinfo=IST),
                                 settings_for_mode("balanced", min_median_turnover=0))
    app = create_app(c, st)
    with TestClient(app) as tc:
        yield tc, c


def _login(tc):
    r = tc.post("/api/auth/login", json={"username": "owner", "password": "correct horse battery"})
    assert r.status_code == 200


def test_auth_required_and_login(client):
    tc, _ = client
    assert tc.get("/api/health").json()["execution_mode"] == "paper"
    assert tc.get("/api/home").status_code == 401
    assert tc.post("/api/auth/login", json={"username": "owner", "password": "wrong"}).status_code == 401
    _login(tc)
    assert tc.get("/api/auth/me").json()["user"] == "owner"


def test_five_screens(client):
    tc, c = client
    _login(tc)
    home = tc.get("/api/home").json()
    assert {"market", "portfolio", "opportunities", "alerts", "risks", "model"} <= set(home)
    assert any("SYNTHETIC" in r["text"] for r in home["risks"])
    inv = tc.post("/api/invest", json={"capital": 20000, "mode": "balanced"}).json()
    assert inv["capital"] == 20000 and "reserve_cash" in inv and "advisory" in inv
    assert tc.post("/api/invest", json={"capital": -5}).status_code == 422
    an = tc.get("/api/analyst/NSE/SYN004").json()
    assert an["chart"] and "thesis" in an and "evidence" in an
    perf = tc.get("/api/performance").json()
    assert perf["ledger_integrity"]["problems"] == [] and "aspiration" in perf
    opp = tc.get("/api/opportunities").json()
    pid = opp["items"][0]["prediction_id"]
    assert tc.get(f"/api/predictions/{pid}").json()["id"] == pid


def test_positions_actual_vs_paper(client):
    tc, c = client
    _login(tc)
    r = tc.post("/api/positions", json={"symbol": "SYN002", "quantity": 10, "avg_price": 500.0, "stop": 450.0,
                                        "target1": 560.0})
    assert r.status_code == 200 and r.json()["kind"] == "actual"
    pos = tc.get("/api/positions").json()
    assert pos["open"][0]["fill_type"].startswith("ACTUAL")
    a = tc.get(f"/api/positions/{r.json()['id']}/assessment").json()
    assert a["action"] in ("HOLD", "EXIT", "PARTIAL_EXIT")
    closed = tc.post(f"/api/positions/{r.json()['id']}/close", json={"exit_price": 510.0}).json()
    assert closed["status"] == "closed"
    assert tc.post("/api/positions", json={"symbol": "NOPE", "quantity": 1, "avg_price": 1}).status_code == 404


def test_push_subscription(client):
    tc, _ = client
    _login(tc)
    assert tc.post("/api/push/subscribe", json={"endpoint": "https://push.example/x",
                                                "keys": {"p256dh": "a", "auth": "b"}}).json()["ok"]
    assert tc.get("/api/push/public-key").json()["enabled"] is False
