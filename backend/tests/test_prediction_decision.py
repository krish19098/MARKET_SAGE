"""Prediction engine, decision layer, allocation and ledger (acceptance tests 1, 2, 5, 13, 14, 15)."""

from datetime import UTC, date, datetime, time

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from market_sage.core.calendar import ExchangeCalendar
from market_sage.core.timeutil import IST
from market_sage.data.providers.fixture import SyntheticMarket
from market_sage.data.service import MarketDataService
from market_sage.db.engine import make_engine, upgrade_to_head
from market_sage.decision.engine import model_context
from market_sage.decision.pipeline import TARGET, DecisionPipeline
from market_sage.features.store import FeatureStore
from market_sage.ledger.ledger import PredictionLedger
from market_sage.models.registry import ModelRegistry
from market_sage.models.targets import ForecastContract, triple_barrier
from market_sage.models.train import build_dataset, train_candidate
from market_sage.portfolio.allocator import allocate, risk_sized_quantity
from market_sage.portfolio.costs import CostModel
from market_sage.portfolio.risk import settings_for_mode

TRAIN_CUTOFF = date(2025, 12, 31)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """SYNTHETIC world with a deliberately planted momentum signal (exercises the skilled-model path)."""
    d = tmp_path_factory.mktemp("world")
    url = f"sqlite:///{d}/w.db"
    upgrade_to_head(url)
    eng = make_engine(url)
    cal = ExchangeCalendar()
    mds = MarketDataService(eng, d / "data", cal)
    market = SyntheticMarket(cal, date(2020, 1, 1), date(2026, 10, 30), n_stocks=16, seed=5, planted_signal=3.0)
    mds.ingest_fixture(market)
    store = FeatureStore(mds)
    reg = ModelRegistry(eng, d / "data")
    model, choice, data = train_candidate(store, TRAIN_CUTOFF, is_synthetic=True, n_folds=3)
    mid = reg.register(model)
    reg.promote(mid, {"reason": "test bootstrap"})
    return {
        "mds": mds,
        "store": store,
        "reg": reg,
        "ledger": PredictionLedger(eng),
        "market": market,
        "model": model,
        "choice": choice,
        "data": data,
        "engine": eng,
    }


def test_triple_barrier_labels_known_only_after_horizon():
    sess = pd.bdate_range("2026-01-01", periods=12).date
    f = pd.DataFrame({"session_date": sess, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "atr14": 2.0})
    f.loc[3, "high"] = 104.0  # upper barrier (entry 100 + 1.5*2 = 103) hit at t=3
    out = triple_barrier(f, ForecastContract())
    assert out.loc[1, "label"] == 1 and out.loc[1, "label_known"] == sess[6]
    assert np.isnan(out.loc[8, "label"])  # not enough future: unknown


def test_dataset_has_no_future_labels(world):
    cutoff = date(2024, 6, 28)
    ds = build_dataset(world["store"], cutoff, ForecastContract())
    assert (ds["label_known"] <= cutoff).all() and (ds["session_date"] < cutoff).all()


def test_walk_forward_purges_and_selects_honestly(world):
    rep = world["choice"].report
    for f in rep.folds:
        assert f.train_end < f.test_start
    assert world["model"].is_synthetic_data
    assert world["choice"].best != "climatology"  # planted signal is learnable
    assert model_context(world["model"]).has_skill


def test_no_skill_model_never_issues_probabilities(mds):
    store = FeatureStore(mds)
    model, choice, _ = train_candidate(
        store, date(2026, 3, 31), is_synthetic=True, n_folds=3, models=("climatology", "momentum_rule", "logistic")
    )
    ctx = model_context(model)
    if choice.best == "climatology":
        assert not ctx.has_skill
    reg = ModelRegistry(mds.engine, mds.data_dir)
    reg.promote(reg.register(model), {"reason": "test"})
    pipe = DecisionPipeline(mds, PredictionLedger(mds.engine), reg)
    cutoff = date(2026, 10, 30)
    res = pipe.evaluate_universe(
        cutoff,
        datetime.combine(cutoff, time(18), tzinfo=IST),
        settings_for_mode("balanced", min_median_turnover=0),
        record=False,
    )
    if not ctx.has_skill:
        assert all(r.action == "AVOID" and r.probabilities is None for r in res.recommendations)
        assert all(any("no validated predictive edge" in x for x in r.reasons) for r in res.recommendations)


def test_stale_data_suppresses_recommendations(world):
    pipe = DecisionPipeline(world["mds"], world["ledger"], world["reg"], store=world["store"])
    cutoff = date(2026, 10, 30)
    late = datetime(2026, 11, 20, 18, 0, tzinfo=IST)  # weeks later, no new bars → stale
    res = pipe.evaluate_universe(cutoff, late, settings_for_mode("balanced", min_median_turnover=0), record=False)
    assert res.recommendations and all(r.suppressed and r.action == "AVOID" for r in res.recommendations)
    assert all("stale" in " ".join(r.reasons) for r in res.recommendations)


def test_end_to_end_buy_recorded_immutably_and_events_linked(world):
    pipe = DecisionPipeline(world["mds"], world["ledger"], world["reg"], store=world["store"])
    settings = settings_for_mode("growth", min_median_turnover=0)
    buys = []
    for cutoff in pd.bdate_range("2026-04-01", "2026-06-30", freq="5B").date:
        now = datetime.combine(cutoff, time(18), tzinfo=IST)
        res = pipe.evaluate_universe(cutoff, now, settings, record=True)
        buys += [(cutoff, r, res.prediction_ids[r.instrument_id]) for r in res.recommendations if r.action == "BUY"]
    assert buys, "skilled synthetic model should produce at least one BUY"
    cutoff, rec, pid = buys[0]
    p = world["ledger"].get(pid)
    # Acceptance 1: all original fields + data cutoff preserved
    assert p["action"] == "BUY" and p["stop"] == rec.plan.stop and p["target1"] == rec.plan.target1
    assert p["data_cutoff"] == datetime.combine(cutoff, time(15, 30), tzinfo=IST).astimezone(UTC)
    assert p["probabilities"]["up"] == pytest.approx(rec.probabilities["up"])
    assert p["provenance"]["synthetic"] is True and p["thesis"]["11_trade_plan"]["stop"] == rec.plan.stop
    # Acceptance 2: new data creates linked events, original unchanged
    before = dict(p)
    world["ledger"].append_event(pid, "price_update", {"ltp": rec.price * 0.97}, datetime.now(UTC))
    world["ledger"].append_event(
        pid, "exit_recommendation", {"action": "EXIT", "price": rec.price * 0.97, "reason": "thesis deteriorated"}
    )
    after = world["ledger"].get(pid)
    assert {k: after[k] for k in before if k != "events"} == {k: before[k] for k in before if k != "events"}
    assert [e["event_type"] for e in after["events"]][-2:] == ["price_update", "exit_recommendation"]
    with pytest.raises(Exception, match="append-only"):
        with world["engine"].begin() as c:
            c.execute(text("UPDATE predictions SET stop = 1 WHERE id = :i"), {"i": pid})
    assert world["ledger"].verify() == []


def test_ledger_detects_tampering(engine, mds):
    led = PredictionLedger(engine)
    iid = mds.instruments.by_symbol("NSE", "SYN001")["id"]
    now = datetime.now(UTC)
    base = {
        "created_at": now,
        "kind": "recommendation",
        "instrument_id": iid,
        "exchange": "NSE",
        "symbol": "SYN001",
        "data_cutoff": now,
        "latest_data_ts": now,
        "data_status": "synthetic",
        "action": "BUY",
        "calibration_status": "test",
        "evidence": [],
        "thesis": {},
        "strategy_version": "t",
        "provenance": {},
    }
    pid = led.record(base)
    led.record(base | {"symbol": "SYN001"})
    led.correct(pid, "target1", 123.0, "data vendor revised close")
    assert led.verify() == []
    # simulate tampering by bypassing triggers (drop → modify) to prove detection works
    from market_sage.db.immutability import drop_immutability_triggers

    with engine.begin() as c:
        drop_immutability_triggers(c, ("predictions",))
        c.execute(text("UPDATE predictions SET action='AVOID' WHERE id=:i"), {"i": pid})
    assert any(p.problem == "content hash mismatch" for p in led.verify())


def test_risk_sizing_and_costs():
    costs = CostModel.load()
    q = risk_sized_quantity(200.0, 100.0, 97.0, costs)
    loss = q * 3 + costs.round_trip(100, 97, q)
    assert loss <= 200 and (q + 1) * 3 + costs.round_trip(100, 97, q + 1) > 200
    leg = costs.leg("sell", 100.0, 10)
    assert leg.dp > 0 and leg.stamp == 0 and not leg.verified


def test_allocation_affordable_quantities_and_cash(world):
    pipe = DecisionPipeline(world["mds"], world["ledger"], world["reg"], store=world["store"])
    settings = settings_for_mode("growth", min_median_turnover=0)
    recs = []
    for cutoff in pd.bdate_range("2026-04-01", "2026-06-30", freq="5B").date:
        res = pipe.evaluate_universe(cutoff, datetime.combine(cutoff, time(18), tzinfo=IST), settings, record=False)
        if any(r.action == "BUY" for r in res.recommendations):
            recs = res.recommendations
            break
    sectors = {i["id"]: i["sector"] for i in world["mds"].instruments.all()}
    alloc = allocate(100000, recs, settings, CostModel.load(), sectors)
    # Acceptance 13: affordable quantities, costs, stop-risk and exposure
    for ln in alloc.lines:
        assert ln.quantity >= 1 and ln.amount <= 100000 * settings.max_position_pct + 1e-6
        assert ln.loss_at_stop <= 100000 * settings.risk_per_trade_pct + 1e-6
    assert alloc.reserve_cash >= 100000 * settings.min_cash_reserve_pct - 1
    assert alloc.total_invested + alloc.total_entry_costs + alloc.reserve_cash == pytest.approx(100000, abs=0.05)
    # Acceptance 14: can leave capital unallocated
    none = allocate(20000, [r for r in recs if r.action != "BUY"], settings, CostModel.load(), sectors)
    assert none.lines == [] and none.reserve_cash == 20000 and any("cash" in n for n in none.notes)
    with pytest.raises(ValueError):
        allocate(0, recs, settings, CostModel.load(), sectors)


def test_model_rollback_preserves_previous(world):
    reg = world["reg"]
    prod = reg.production_row(TARGET)
    cand_id = reg.register(
        world["model"].__class__(**{**world["model"].__dict__, "version": world["model"].version + "-b"})
    )
    reg.promote(cand_id, {"reason": "test"})
    assert reg.production_row(TARGET)["id"] == cand_id
    restored = reg.rollback(TARGET)
    assert restored == prod["id"] and reg.production_row(TARGET)["id"] == prod["id"]


def test_estimators_ignore_features_never_observed():
    """An all-missing feature (e.g. sector RS before sector mapping) must not break any learner."""
    from market_sage.models.estimators import make_estimator

    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(size=600), "b": rng.normal(size=600), "empty": np.nan})
    y = rng.choice([-1, 0, 1], size=600)
    for name in ("logistic", "random_forest", "hgb"):
        p = make_estimator(name).fit(X, y).predict_proba(X)
        assert p.shape == (600, 3) and np.allclose(p.sum(axis=1), 1.0)
