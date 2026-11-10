"""Monitoring, alerts, notifications, evaluation, learning and paper trading
(acceptance tests 3, 4, 6, 7, 8, 9, 10, 11, 12, 16, 17, 18)."""

import asyncio
from datetime import UTC, date, datetime, time, timedelta

import pandas as pd
import pytest
from sqlalchemy import insert, select

from market_sage.core.timeutil import IST
from market_sage.db import schema as s
from market_sage.evaluation.performance import PerformanceService, aspiration_requirements
from market_sage.evaluation.scoring import Evaluator, score_prediction
from market_sage.execution.paper import PaperBroker
from market_sage.features.store import FeatureStore
from market_sage.learning.controlled import GateCriteria, run_learning_cycle
from market_sage.ledger.ledger import PredictionLedger
from market_sage.models.registry import ModelRegistry
from market_sage.monitoring.positions import PositionRepo
from market_sage.monitoring.rules import assess_position
from market_sage.monitoring.service import MonitorService, token_map_for
from market_sage.notifications.alerts import AlertStore
from market_sage.notifications.push import Notifier
from market_sage.portfolio.costs import CostModel


def _services(mds, sender=None):
    store = FeatureStore(mds)
    led = PredictionLedger(mds.engine)
    mon = MonitorService(mds, store, PositionRepo(mds.engine), AlertStore(mds.engine),
                         Notifier(mds.engine, sender, sleep=lambda _: None), led)
    return store, led, mon


def _pred(mds, led, symbol, cutoff, price, stop, t1, t2, action="BUY", probs=None):
    inst = mds.instruments.by_symbol("NSE", symbol)
    co = datetime.combine(cutoff, time(15, 30), tzinfo=IST)
    return led.record({"created_at": co + timedelta(hours=3), "kind": "recommendation", "instrument_id": inst["id"],
                       "exchange": "NSE", "symbol": symbol, "data_cutoff": co, "latest_data_ts": co,
                       "data_status": "synthetic", "price_at_prediction": price, "action": action, "direction": "up",
                       "entry_low": price * 0.99, "entry_high": price * 1.01, "stop": stop, "target1": t1, "target2": t2,
                       "horizon_sessions": 5, "probabilities": probs, "calibration_status": "test",
                       "evidence": [{"category": "structure", "kind": "fact", "stance": "bullish",
                                     "statement": "test evidence", "value": None}],
                       "thesis": {"10_expected_return_and_downside": {"p10": -0.05, "median": 0.01, "p90": 0.06}},
                       "strategy_version": "test", "provenance": {"synthetic": True}})


def test_state_machine_distinguishes_stages():
    pos = {"id": 1, "symbol": "X", "avg_price": 100.0, "stop": 95.0, "target1": 107.0, "target2": 112.0,
           "monitor_state": "normal"}
    a = assess_position(pos, 96.0, 2.0, None, intraday=True)
    assert a.state == "approaching_stop" and a.alerts[0]["stage"] == "approaching" and a.action == "HOLD"
    b = assess_position(pos, 94.5, 2.0, None, intraday=True)
    assert b.state == "stop_triggered" and b.alerts[0]["stage"] == "confirmed" and b.action == "EXIT"
    c = assess_position(pos, 108.0, 2.0, None, intraday=False)
    assert c.action == "PARTIAL_EXIT" and {x["alert_class"] for x in c.alerts} == {"target_hit", "partial_profit"}
    assert assess_position(pos, 101.0, 2.0, None, intraday=False).alerts == []  # no alert for noise


def test_early_warning_precedes_confirmed_stop(mds, market):
    """Acceptance 3 & 4: replay a decline day by day; early/approaching alert must come before the stop trigger."""
    store, led, mon = _services(mds)
    iid = mds.instruments.by_symbol("NSE", "SYN007")["id"]
    f = store.instrument_features(iid)
    # find a window with a meaningful decline from a local high
    closes = f["close"].to_numpy()
    start = next(i for i in range(300, len(f) - 15) if closes[i + 10] < closes[i] * 0.9)
    entry = float(closes[start])
    atr = float(f["atr14"].iloc[start])
    pos_id = PositionRepo(mds.engine).open(kind="paper", instrument_id=iid, exchange="NSE", symbol="SYN007",
                                           quantity=10, avg_price=entry, stop=entry - 2.0 * atr,
                                           target1=entry + 3 * atr, target2=entry + 5 * atr)
    seen = []
    for k in range(start + 1, start + 15):
        d = f["session_date"].iloc[k]
        pos = PositionRepo(mds.engine).get(pos_id)
        if pos["status"] != "open":
            break
        ff = store.instrument_features(iid, until=d)
        a = assess_position(pos, float(ff["close"].iloc[-1]), float(ff["atr14"].iloc[-1]), ff, intraday=False)
        PositionRepo(mds.engine).set_state(pos_id, a.state)
        for al in a.alerts:
            seen.append((k, al["stage"], al["alert_class"]))
        if a.state == "stop_triggered":
            break
    stages = [x[1] for x in seen]
    assert "confirmed" in stages, seen
    first_conf = next(k for k, st, _ in seen if st == "confirmed")
    assert any(k < first_conf and st in ("early_warning", "approaching") for k, st, _ in seen), seen


def test_monitoring_runs_without_any_client_and_records_delivery_failures(mds, market):
    """Acceptance 16 & 17: backend monitor consumes a feed with no browser; push failures are logged."""
    calls = []

    def failing_sender(sub, payload):
        calls.append(payload)
        raise RuntimeError("push service unavailable")

    store, led, mon = _services(mds, failing_sender)
    with mds.engine.begin() as c:
        c.execute(insert(s.push_subscriptions).values(endpoint="https://push.example/abc", keys={"p256dh": "x", "auth": "y"},
                                                      created_at=datetime.now(UTC), active=True))
    iid = mds.instruments.by_symbol("NSE", "SYN002")["id"]
    last = float(mds.daily_bars(iid)["close"].iloc[-1])
    PositionRepo(mds.engine).open(kind="actual", instrument_id=iid, exchange="NSE", symbol="SYN002", quantity=5,
                                  avg_price=last * 1.02, stop=last * 1.01, target1=last * 1.2, target2=last * 1.3)
    insts = [i for i in market.list_instruments() if i.symbol == "SYN002"]
    n = asyncio.run(mon.run_live(market.stream(insts, interval_s=0.0, max_ticks=3), token_map_for(mds, "fixture", insts),
                                 eval_every_s=0.0, stop_after=3))
    assert n == 3
    alerts = AlertStore(mds.engine).recent()
    assert any(a["alert_class"] == "stop_triggered" and a["stage"] == "confirmed" for a in alerts)
    with mds.engine.connect() as c:
        deliveries = c.execute(select(s.notification_deliveries)).fetchall()
    assert deliveries and all(d.status == "failed" for d in deliveries) and len(calls) == 3  # 3 attempts logged
    # dedupe: same condition does not re-alert within cooldown
    n_before = len(AlertStore(mds.engine).recent())
    asyncio.run(mon.run_live(market.stream(insts, interval_s=0.0, max_ticks=2), token_map_for(mds, "fixture", insts),
                             eval_every_s=0.0, stop_after=2))
    assert len(AlertStore(mds.engine).recent()) == n_before


def test_feed_outage_alert(mds):
    _, _, mon = _services(mds)
    aid = mon.check_feed(datetime.now(UTC), market_open=True)
    assert aid is not None
    assert AlertStore(mds.engine).recent()[0]["alert_class"] == "data_stale"


def test_multi_horizon_evaluation_and_lessons(mds, market):
    """Acceptance 9 & 10: horizons scored separately with direction/timing/calibration components."""
    store, led, _ = _services(mds)
    iid = mds.instruments.by_symbol("NSE", "SYN003")["id"]
    bars = mds.daily_bars(iid)
    cut = bars["session_date"].iloc[-40]
    px = float(bars.loc[bars["session_date"] == cut, "close"].iloc[0])
    pid = _pred(mds, led, "SYN003", cut, px, px * 0.95, px * 1.04, px * 1.08, probs={"up": 0.5, "neutral": 0.2, "down": 0.3})
    n = Evaluator(mds, store).evaluate_pending()
    with mds.engine.connect() as c:
        ev = {r.horizon: r.metrics for r in c.execute(select(s.evaluations).where(s.evaluations.c.prediction_id == pid))}
        les = c.execute(select(s.lessons)).fetchall()
    assert n >= 5 and set(ev) == {"1s", "3s", "5s", "10s", "20s"}
    m5 = ev["5s"]
    assert {"direction_correct", "entry", "target", "stop_quality", "brier", "barrier_outcome"} <= set(m5)
    assert les and les[0].error_cause in {"data", "feature", "regime", "model", "execution", "risk", "event", "unknown"}
    assert Evaluator(mds, store).evaluate_pending() == 0  # idempotent, append-only
    summ = PerformanceService(mds.engine).summary()
    assert summ["by_horizon"]["5s"]["buy_direction_accuracy"]["n"] == 1


def test_exit_counterfactuals_loss_avoided_and_upside_missed(mds):
    """Acceptance 5, 6, 7, 8: exit keeps original record; avoided loss / missed upside computed separately."""
    store, led, _ = _services(mds)
    iid = mds.instruments.by_symbol("NSE", "SYN006")["id"]
    bars = mds.daily_bars(iid)
    cut = bars["session_date"].iloc[-60]
    px = float(bars.loc[bars["session_date"] == cut, "close"].iloc[0])
    pid = _pred(mds, led, "SYN006", cut, px, px * 0.9, px * 1.1, px * 1.2)
    exit_session = bars["session_date"].iloc[-50]
    exit_px = float(bars.loc[bars["session_date"] == exit_session, "close"].iloc[0])
    led.append_event(pid, "exit_recommendation", {"action": "EXIT", "price": exit_px, "session": str(exit_session)})
    orig = led.get(pid)
    res = Evaluator(mds, store).evaluate_exit(orig, exit_px, exit_session, 10, entry_price=px)
    after = bars[bars["session_date"] > exit_session].head(10)
    assert res["max_adverse_move_avoided_per_share"] == pytest.approx(max(0, exit_px - after["low"].min()))
    assert res["potential_upside_missed_per_share"] == pytest.approx(max(0, after["high"].max() - exit_px))
    assert "COUNTERFACTUAL" in res["basis"]
    assert "possible" in res["earlier_warning"] and "alternative_trailing" in res
    confirmed = Evaluator(mds, store).evaluate_exit(orig, exit_px, exit_session, 10, actual_fill=exit_px - 1)
    assert confirmed["basis"] == "confirmed user fill"
    assert led.get(pid)["price_at_prediction"] == px  # original untouched


def test_spec_example_loss_avoided():
    """Entry 250, exit 246, later 225 → ₹21/share decline avoided (counterfactual)."""
    pred = {"price_at_prediction": 250.0, "action": "BUY", "entry_low": 249, "entry_high": 251, "stop": 240,
            "target1": 265, "target2": 275, "probabilities": None}
    path = pd.DataFrame({"session_date": pd.bdate_range("2026-01-01", periods=5).date, "open": [248, 246, 240, 230, 226],
                         "high": [249, 247, 241, 231, 227], "low": [246, 239, 229, 225, 225], "close": [246, 240, 230, 226, 225]})
    sc = score_prediction(pred, path, 5)
    assert sc["barrier_outcome"] == "stop"
    assert 246 - path["low"].min() == 21


def test_learning_cycle_rejects_no_skill_candidate_and_keeps_production(mds):
    """Acceptance 11 & 12 on no-signal SYNTHETIC data: candidate judged on unseen holdout; rejected; production intact."""
    store = FeatureStore(mds)
    reg = ModelRegistry(mds.engine, mds.data_dir)
    res = run_learning_cycle(store, reg, date(2026, 10, 1), is_synthetic=True, n_folds=3,
                             criteria=GateCriteria(holdout_sessions=40))
    assert res.gate_report["train_end"] < res.gate_report["holdout_start"]
    assert not res.promoted and res.gate_report["failed_checks"]
    assert reg.production_row("tb5_atr") is None
    assert reg.get(res.candidate_id)["status"] == "rejected"


def test_paper_trading_entry_rules_and_user_vs_paper(mds):
    """Acceptance 18: paper (simulated) positions distinct from user-entered actual positions."""
    store, led, _ = _services(mds)
    iid = mds.instruments.by_symbol("NSE", "SYN001")["id"]
    bars = mds.daily_bars(iid)
    cut = bars["session_date"].iloc[-30]
    px = float(bars.loc[bars["session_date"] == cut, "close"].iloc[0])
    pid = _pred(mds, led, "SYN001", cut, px, px * 0.95, px * 1.03, px * 1.06)
    broker = PaperBroker(mds.engine, mds, led, CostModel.load())
    nxt = bars["session_date"].iloc[-29]
    pos_id = broker.try_entry(led.get(pid), 10, nxt)
    fills = broker.fills()
    assert fills[0]["status"] in ("filled", "missed")
    if pos_id:
        assert PositionRepo(mds.engine).get(pos_id)["kind"] == "paper"
        for d in bars["session_date"].iloc[-28:]:
            broker.mark_session(d)
        assert PositionRepo(mds.engine).get(pos_id)["status"] == "closed"
    with pytest.raises(ValueError):
        PositionRepo(mds.engine).open(kind="live", instrument_id=iid, exchange="NSE", symbol="SYN001", quantity=1,
                                      avg_price=1.0)


def test_aspiration_is_shown_as_requirement_not_promise():
    req = aspiration_requirements()
    r20 = next(r for r in req if r["capital"] == 20000)
    assert r20["required_annual_return"] == pytest.approx(500 * 245 / 20000)
