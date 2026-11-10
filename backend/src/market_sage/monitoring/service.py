"""Always-on monitoring service (runs in the backend worker, independent of any browser or phone).

Consumes live quotes (WebSocket stream or polling) when available, otherwise end-of-day data; assesses
every open position; emits staged, deduplicated alerts; records linked ledger events; and fails safe
(stale feed → outage alert + live-dependent assessments flagged).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from market_sage.core.timeutil import utcnow
from market_sage.data.models import DataStatus, FeedStatus, ProviderInstrument, Quote
from market_sage.data.service import MarketDataService
from market_sage.decision.pipeline import PipelineResult
from market_sage.features.store import FeatureStore
from market_sage.ledger.ledger import PredictionLedger
from market_sage.monitoring.positions import PositionRepo
from market_sage.monitoring.rules import Assessment, assess_position
from market_sage.notifications.alerts import AlertDraft, AlertStore
from market_sage.notifications.push import Notifier


@dataclass
class FeedHealth:
    stale_after: timedelta
    connected: bool = False
    last_tick_at: datetime | None = None
    last_status: str = "no live feed configured"
    latencies_ms: list[float] = field(default_factory=list)

    def on_tick(self, q: Quote) -> None:
        self.last_tick_at = q.received_ts
        self.latencies_ms = (self.latencies_ms + [(q.received_ts - q.source_ts).total_seconds() * 1000])[-200:]

    def on_status(self, st: FeedStatus) -> None:
        self.connected, self.last_status = st.connected, st.message

    def is_stale(self, now: datetime) -> bool:
        return (not self.connected) or self.last_tick_at is None or now - self.last_tick_at > self.stale_after

    def snapshot(self, now: datetime) -> dict:
        lat = self.latencies_ms
        return {"connected": self.connected, "last_tick_at": self.last_tick_at, "stale": self.is_stale(now),
                "status": self.last_status, "median_latency_ms": float(np.median(lat)) if lat else None}


class MonitorService:
    def __init__(self, mds: MarketDataService, store: FeatureStore, positions: PositionRepo, alerts: AlertStore,
                 notifier: Notifier, ledger: PredictionLedger, stale_after_s: int = 120) -> None:
        self.mds, self.store, self.positions, self.alerts = mds, store, positions, alerts
        self.notifier, self.ledger = notifier, ledger
        self.feed = FeedHealth(timedelta(seconds=stale_after_s))
        self._last_eval: dict[int, datetime] = {}

    # --- alerts ------------------------------------------------------------------------------
    def _emit(self, d: AlertDraft, now: datetime) -> int | None:
        aid = self.alerts.create(d, now)
        if aid is not None:
            alert = next(a for a in self.alerts.recent(5) if a["id"] == aid)
            self.notifier.deliver(alert)
            if d.prediction_id:
                self.ledger.append_event(d.prediction_id, "alert", {"alert_id": aid, "class": d.alert_class,
                                                                    "stage": d.stage, "message": d.message},
                                         d.data_cutoff, created_at=now)
        return aid

    # --- positions ---------------------------------------------------------------------------
    def price_for(self, iid: int, now: datetime, market_open: bool) -> tuple[float, str, datetime | None]:
        q = self.mds.latest_quote(iid)
        if q is not None and now - q.received_ts <= self.feed.stale_after:
            return q.ltp, q.status.value, q.source_ts
        bars = self.mds.daily_bars(iid)
        if bars.empty:
            return float("nan"), DataStatus.STALE.value, None
        last = bars.iloc[-1]
        status = DataStatus.STALE.value if market_open else self.mds.data_status(iid, now).value
        return float(last["close"]), status, last["source_ts"]

    def assess_all(self, now: datetime, market_open: bool = False) -> list[tuple[dict, Assessment]]:
        out = []
        for pos in self.positions.list("open"):
            out.append((pos, self.assess_one(pos, now, market_open)))
        return out

    def assess_one(self, pos: dict, now: datetime, market_open: bool) -> Assessment:
        iid = pos["instrument_id"]
        price, status, src_ts = self.price_for(iid, now, market_open)
        latest = self.mds.latest_session(iid)
        f = self.store.instrument_features(iid, until=latest) if latest else None
        atr = float(f["atr14"].iloc[-1]) if f is not None and len(f) else float("nan")
        a = assess_position(pos, price, atr, f, intraday=market_open)
        if status == DataStatus.STALE.value:
            a.reasons.append("price data stale — assessment uses last known close; live triggers suspended")
            a.alerts = [x for x in a.alerts if x["stage"] != "confirmed" or not market_open]
        prev = pos.get("monitor_state")
        if a.state != prev:
            self.positions.set_state(pos["id"], a.state)
        pid = pos.get("source_prediction_id")
        for al in a.alerts:
            self._emit(AlertDraft(al["alert_class"], al["stage"], al["title"], al["message"], al["key"],
                                  instrument_id=iid, symbol=pos["symbol"], prediction_id=pid, position_id=pos["id"],
                                  data_cutoff=src_ts, evidence={"price": price, "data_status": status,
                                                                "position_kind": pos["kind"], "reasons": a.reasons},
                                  invalidation=f"stop {pos.get('stop')}"), now)
        if pid and (a.state != prev or a.action != "HOLD"):
            etype = "exit_recommendation" if a.action in ("EXIT", "PARTIAL_EXIT") else "reassessment"
            self.ledger.append_event(pid, etype, a.to_dict() | {"price": price, "data_status": status,
                                                                "position_id": pos["id"]}, src_ts, created_at=now)
        return a

    # --- market-level checks -------------------------------------------------------------------
    def check_feed(self, now: datetime, market_open: bool) -> int | None:
        if market_open and self.feed.is_stale(now):
            return self._emit(AlertDraft("data_stale", "confirmed", "Live market data stale or disconnected",
                                         f"Feed status: {self.feed.last_status}. Last tick: {self.feed.last_tick_at}. "
                                         "Recommendations needing live data are suspended.",
                                         f"feed_stale:{now:%Y%m%d%H}"), now)
        return None

    def check_regime(self, cutoff: date, now: datetime) -> int | None:
        idx = self.store.index_instrument()
        if idx is None:
            return None
        sample = next((i for i in self.mds.instruments.all(include_indices=False)), None)
        if sample is None:
            return None
        f = self.store.instrument_features(sample["id"], until=cutoff)
        if len(f) < 2 or f["regime_trend"].iloc[-1] == f["regime_trend"].iloc[-2]:
            return None
        old, new = f["regime_trend"].iloc[-2], f["regime_trend"].iloc[-1]
        return self._emit(AlertDraft("regime_change", "confirmed" if new != "unknown" else "info",
                                     f"Market regime changed: {old} → {new}",
                                     f"Index regime classification changed at the {cutoff} close "
                                     f"(confidence {f['regime_confidence'].iloc[-1]:.2f}). Regime labels are estimates.",
                                     f"regime:{cutoff}:{new}", instrument_id=idx["id"], symbol=idx["symbol"]), now)

    def announce_recommendations(self, res: PipelineResult, now: datetime, max_early: int = 5) -> list[int]:
        ids = []
        for r in res.recommendations:
            pid = res.prediction_ids.get(r.instrument_id)
            if r.action == "BUY" and r.plan:
                prob = (r.probabilities or {}).get("up")
                aid = self._emit(AlertDraft(
                    "new_buy", "info", f"{r.symbol}: new BUY recommendation (advisory)",
                    f"Entry {r.plan.entry_low}-{r.plan.entry_high}, stop {r.plan.stop}, T1 {r.plan.target1}. "
                    f"P(target before stop) {prob:.0%} (calibrated OOS)." if prob else "BUY (see analysis).",
                    f"buy:{r.instrument_id}:{res.cutoff}", instrument_id=r.instrument_id, symbol=r.symbol,
                    prediction_id=pid, probability=prob, invalidation=f"close below {r.plan.stop}"), now)
                if aid:
                    ids.append(aid)
        early = [(r, s) for r in res.recommendations if not r.suppressed for s in r.setups
                 if s.stage == "early" and s.direction in ("bullish", "bearish")]
        for r, s in early[:max_early]:
            cls = "early_bullish" if s.direction == "bullish" else "early_bearish"
            aid = self._emit(AlertDraft(cls, "early_warning", f"{r.symbol}: early {s.direction} development ({s.name})",
                                        f"{s.detail}. Developing condition — not confirmed."
                                        + (f" Trigger {s.trigger:.2f}." if s.trigger else ""),
                                        f"{cls}:{r.instrument_id}:{s.name}:{res.cutoff}", instrument_id=r.instrument_id,
                                        symbol=r.symbol, prediction_id=res.prediction_ids.get(r.instrument_id),
                                        invalidation=f"{s.invalidation:.2f}" if s.invalidation else None), now)
            if aid:
                ids.append(aid)
        return ids

    # --- live loop -----------------------------------------------------------------------------
    async def run_live(self, stream: AsyncIterator[Quote | FeedStatus], token_map: dict[str, int],
                       eval_every_s: float = 30.0, stop_after: int | None = None) -> int:
        """Consume a live stream: record quotes, update feed health, assess affected positions (throttled)."""
        n = 0
        open_ids = {p["instrument_id"] for p in self.positions.list("open")}
        async for item in stream:
            now = utcnow()
            if isinstance(item, FeedStatus):
                self.feed.on_status(item)
                if not item.connected:
                    self.check_feed(now, True)
                continue
            iid = token_map.get(item.provider_token)
            if iid is None:
                continue
            q = Quote(iid, item.ltp, item.source_ts, item.received_ts, item.provider, item.open, item.high, item.low,
                      item.prev_close, item.volume, item.status, item.provider_token)
            self.mds.record_quote(q)
            self.feed.on_tick(q)
            if iid in open_ids and (iid not in self._last_eval
                                    or (now - self._last_eval[iid]).total_seconds() >= eval_every_s):
                self._last_eval[iid] = now
                for pos in self.positions.list("open"):
                    if pos["instrument_id"] == iid:
                        self.assess_one(pos, now, market_open=True)
            n += 1
            if stop_after is not None and n >= stop_after:
                break
        return n


def token_map_for(mds: MarketDataService, provider: str, instruments: Sequence[ProviderInstrument]) -> dict[str, int]:
    out = {}
    for inst in instruments:
        row = mds.instruments.by_symbol(inst.exchange, inst.symbol)
        if row:
            out[inst.provider_token] = row["id"]
    return out

