"""Service wiring shared by the API, the worker and the CLI (one instance per process)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Engine, select

from market_sage.core.calendar import ExchangeCalendar
from market_sage.core.config import Settings, get_settings
from market_sage.data.service import MarketDataService
from market_sage.db import schema as s
from market_sage.db.engine import make_engine
from market_sage.decision.engine import Recommendation, TradePlan
from market_sage.decision.pipeline import DecisionPipeline
from market_sage.evaluation.performance import PerformanceService
from market_sage.evaluation.scoring import Evaluator
from market_sage.execution.paper import PaperBroker
from market_sage.features.store import FeatureStore
from market_sage.ledger.ledger import PredictionLedger
from market_sage.models.registry import ModelRegistry
from market_sage.monitoring.positions import PositionRepo
from market_sage.monitoring.service import MonitorService
from market_sage.notifications.alerts import AlertStore
from market_sage.notifications.push import Notifier, webpush_sender
from market_sage.portfolio.costs import CostModel


@dataclass
class Container:
    settings: Settings
    engine: Engine
    mds: MarketDataService
    store: FeatureStore
    ledger: PredictionLedger
    registry: ModelRegistry
    costs: CostModel
    pipeline: DecisionPipeline
    positions: PositionRepo
    alerts: AlertStore
    notifier: Notifier
    monitor: MonitorService
    evaluator: Evaluator
    performance: PerformanceService
    paper: PaperBroker
    extras: dict = field(default_factory=dict)

    @classmethod
    def build(cls, settings: Settings | None = None, engine: Engine | None = None) -> Container:
        settings = settings or get_settings()
        engine = engine or make_engine(settings.database_url)
        mds = MarketDataService(engine, settings.data_dir, ExchangeCalendar.load())
        store = FeatureStore(mds)
        ledger = PredictionLedger(engine)
        registry = ModelRegistry(engine, settings.data_dir)
        costs = CostModel.load()
        notifier = Notifier(engine, webpush_sender(settings))
        positions = PositionRepo(engine)
        alerts = AlertStore(engine)
        return cls(settings, engine, mds, store, ledger, registry, costs,
                   DecisionPipeline(mds, ledger, registry, costs, store), positions, alerts, notifier,
                   MonitorService(mds, store, positions, alerts, notifier, ledger, settings.live_stale_after_s),
                   Evaluator(mds, store), PerformanceService(engine), PaperBroker(engine, mds, ledger, costs))

    # --- read helpers ------------------------------------------------------------------------
    def latest_cutoff(self) -> date | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(s.predictions.c.data_cutoff).order_by(s.predictions.c.seq.desc()).limit(1)).first()
        if row is None:
            return None
        from market_sage.evaluation.scoring import session_of

        return session_of(row.data_cutoff)

    def predictions_for_cutoff(self, cutoff: date) -> list[dict]:
        from market_sage.analysis.analyst import cutoff_datetime

        with self.engine.connect() as conn:
            rows = conn.execute(select(s.predictions).where(s.predictions.c.data_cutoff == cutoff_datetime(cutoff))
                                .order_by(s.predictions.c.seq)).fetchall()
        latest: dict[int, dict] = {}
        for r in rows:  # if re-run for the same cutoff, the latest record per instrument wins (all remain stored)
            latest[r.instrument_id] = dict(r._mapping)
        return list(latest.values())


def recommendation_from_ledger(p: dict) -> Recommendation:
    """Rebuild an allocatable recommendation from its immutable ledger record (allocation = what was recorded)."""
    plan_d = p.get("plan") or {}
    plan = None
    if p.get("stop") is not None:
        plan = TradePlan(p["entry_low"], p["entry_high"], p["stop"], p["target1"], p["target2"], p["horizon_sessions"],
                         tuple(plan_d.get("horizon_range", [3, 10])), plan_d.get("reward_risk_t1", 0.0),
                         plan_d.get("per_share_risk", p["price_at_prediction"] - p["stop"]),
                         plan_d.get("entry_rule", ""), plan_d.get("partial_booking", ""), plan_d.get("gap_risk_note", ""))
    ev = (p.get("uncertainty") or {}).get("expected_value_per_share")
    q = ev / plan.per_share_risk if (ev is not None and plan and plan.per_share_risk) else None
    return Recommendation(p["instrument_id"], p["symbol"], p["action"], p.get("direction") or "neutral",
                          p["price_at_prediction"], p["data_status"], plan, p.get("probabilities"),
                          p["calibration_status"], ev, q, p["kind"] == "suppressed", plan_d.get("reasons", []), [],
                          p.get("thesis") or {}, [], plan_d.get("liquidity", {"adv_20d": 0.0, "median_turnover_20d": 0.0,
                                                                               "price": p["price_at_prediction"]}),
                          p.get("model_version"))
