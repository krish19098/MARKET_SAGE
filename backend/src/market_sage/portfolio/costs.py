"""Indian cash-equity transaction cost model from a versioned charge schedule.

The schedule's ``verified`` flag is propagated to every estimate so the UI can label costs as
estimated-from-unverified-schedule until reconciled with a broker contract note.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SCHEDULE = Path(__file__).resolve().parents[1] / "resources" / "costs" / "charges_v1.json"


@dataclass(frozen=True)
class CostBreakdown:
    brokerage: float
    stt: float
    exchange: float
    sebi: float
    stamp: float
    gst: float
    dp: float
    slippage: float
    schedule_version: str
    verified: bool

    @property
    def statutory_and_fees(self) -> float:
        return self.brokerage + self.stt + self.exchange + self.sebi + self.stamp + self.gst + self.dp

    @property
    def total(self) -> float:
        return self.statutory_and_fees + self.slippage

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["total"] = round(self.total, 2)
        return d


class CostModel:
    def __init__(self, schedule: dict) -> None:
        self.s = schedule

    @classmethod
    def load(cls, path: Path = DEFAULT_SCHEDULE) -> CostModel:
        return cls(json.loads(path.read_text()))

    @property
    def version(self) -> str:
        return str(self.s["version"])

    @property
    def verified(self) -> bool:
        return bool(self.s.get("verified", False))

    def leg(
        self, side: str, price: float, qty: int, product: str = "delivery", include_slippage: bool = True
    ) -> CostBreakdown:
        p = self.s[product]
        value = price * qty
        brokerage = min(value * p["brokerage_pct"], p["brokerage_cap"])
        brokerage = max(brokerage, p.get("brokerage_min", 0.0)) if qty > 0 else 0.0
        stt = value * (p["stt_buy_pct"] if side == "buy" else p["stt_sell_pct"])
        exch = value * p["exchange_txn_pct"]
        sebi = value * p["sebi_fee_pct"]
        stamp = value * p["stamp_buy_pct"] if side == "buy" else 0.0
        gst = (brokerage + exch + sebi) * p["gst_pct"]
        dp = p["dp_charge_per_sell"] * (1 + p["gst_pct"]) if side == "sell" and qty > 0 else 0.0
        slip = value * self.s["slippage_pct"] if include_slippage else 0.0
        return CostBreakdown(brokerage, stt, exch, sebi, stamp, gst, dp, slip, self.version, self.verified)

    def round_trip(self, entry: float, exit_: float, qty: int, product: str = "delivery") -> float:
        return self.leg("buy", entry, qty, product).total + self.leg("sell", exit_, qty, product).total
