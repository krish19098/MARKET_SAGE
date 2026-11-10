"""End-of-day decision pipeline: analysis → setups → decision → immutable ledger entries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from market_sage.analysis.analyst import Analyst, cutoff_datetime
from market_sage.core.timeutil import utcnow
from market_sage.data.models import Interval
from market_sage.data.service import MarketDataService
from market_sage.decision.engine import (
    STRATEGY_VERSION,
    ModelContext,
    Recommendation,
    decide,
    liquidity_stats,
    model_context,
)
from market_sage.features.builder import FEATURE_SET_VERSION, MODEL_FEATURES
from market_sage.features.store import FeatureStore
from market_sage.ledger.ledger import PredictionLedger
from market_sage.models.registry import ModelRegistry
from market_sage.models.setups import detect_setups
from market_sage.portfolio.costs import CostModel
from market_sage.portfolio.risk import RiskSettings

TARGET = "tb5_atr"


@dataclass
class PipelineResult:
    cutoff: date
    recommendations: list[Recommendation]
    prediction_ids: dict[int, str]
    model_note: str


class DecisionPipeline:
    def __init__(
        self,
        mds: MarketDataService,
        ledger: PredictionLedger,
        registry: ModelRegistry,
        costs: CostModel | None = None,
        store: FeatureStore | None = None,
    ) -> None:
        self.mds, self.ledger, self.registry = mds, ledger, registry
        self.store = store or FeatureStore(mds)
        self.analyst = Analyst(self.store)
        self.costs = costs or CostModel.load()

    def model_ctx(self) -> ModelContext:
        return model_context(self.registry.load_production(TARGET))

    def evaluate_universe(
        self,
        cutoff: date,
        now: datetime,
        settings: RiskSettings,
        instrument_ids: list[int] | None = None,
        record: bool = True,
    ) -> PipelineResult:
        mctx = self.model_ctx()
        ids = instrument_ids or [i["id"] for i in self.mds.instruments.all(include_indices=False)]
        pool = self.store.universe_features(until=cutoff)
        recs: list[Recommendation] = []
        pids: dict[int, str] = {}
        for iid in ids:
            rec = self.evaluate(iid, cutoff, now, settings, mctx, pool)
            if rec is None:
                continue
            recs.append(rec)
            if record:
                pids[iid] = self.record(rec, cutoff, now, settings)
        return PipelineResult(cutoff, recs, pids, mctx.skill_note)

    def evaluate(
        self,
        iid: int,
        cutoff: date,
        now: datetime,
        settings: RiskSettings,
        mctx: ModelContext | None = None,
        pool: pd.DataFrame | None = None,
    ) -> Recommendation | None:
        mctx = mctx or self.model_ctx()
        rep = self.analyst.analyse(iid, cutoff, pool)
        if rep is None:
            return None
        f = self.store.instrument_features(iid, until=cutoff)
        complete = bool(rep.row[MODEL_FEATURES[:20]].notna().all())
        return decide(
            rep,
            self.mds.data_status(iid, now),
            mctx,
            settings,
            self.costs,
            detect_setups(f),
            liquidity_stats(f),
            features_complete=complete,
        )

    def record(
        self, rec: Recommendation, cutoff: date, now: datetime, settings: RiskSettings, parent: str | None = None
    ) -> str:
        inst = self.mds.instruments.get(rec.instrument_id)
        assert inst is not None
        bars = self.mds.bars.read(inst["exchange"], Interval.D1, rec.instrument_id)
        last = bars[bars["session_date"] <= cutoff].iloc[-1]
        plan = rec.plan
        provenance = {
            "providers": sorted(set(bars["provider"].dropna())),
            "latest_bar_provider": last["provider"],
            "latest_raw_file_id": None if last["raw_file_id"] is None else int(last["raw_file_id"]),
            "synthetic": bool((bars["provider"] == "fixture").any()),
            "costs_schedule": self.costs.version,
            "costs_verified": self.costs.verified,
        }
        return self.ledger.record(
            {
                "created_at": now if now else utcnow(),
                "kind": rec.kind,
                "instrument_id": rec.instrument_id,
                "exchange": inst["exchange"],
                "symbol": rec.symbol,
                "data_cutoff": cutoff_datetime(cutoff),
                "latest_data_ts": last["source_ts"],
                "data_status": rec.data_status,
                "price_at_prediction": rec.price,
                "action": rec.action,
                "direction": rec.direction,
                "entry_low": plan.entry_low if plan else None,
                "entry_high": plan.entry_high if plan else None,
                "stop": plan.stop if plan else None,
                "target1": plan.target1 if plan else None,
                "target2": plan.target2 if plan else None,
                "horizon_sessions": plan.horizon_sessions if plan else None,
                "probabilities": rec.probabilities,
                "calibration_status": rec.calibration_status,
                "uncertainty": {
                    "analogue_range": rec.thesis.get("10_expected_return_and_downside"),
                    "expected_value_per_share": rec.expected_value_per_share,
                },
                "evidence": [e.to_dict() for e in rec.evidence],
                "thesis": rec.thesis,
                "invalidation": f"Daily close below {plan.stop:.2f}" if plan else None,
                "plan": (
                    plan.to_dict()
                    | {"setups": [s.to_dict() for s in rec.setups], "reasons": rec.reasons, "liquidity": rec.liquidity}
                )
                if plan
                else {"reasons": rec.reasons},
                "model_version": rec.model_version,
                "feature_set_version": FEATURE_SET_VERSION,
                "strategy_version": STRATEGY_VERSION,
                "risk_settings_version": settings.version,
                "provenance": provenance,
                "parent_prediction_id": parent,
            }
        )
