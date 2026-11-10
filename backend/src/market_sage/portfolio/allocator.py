"""Budget-based allocation: rank validated opportunities, size by risk, respect exposure/correlation limits,
include costs, keep reserve cash, and explain every selection and rejection. 100% cash is a valid result."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from market_sage.decision.engine import Recommendation
from market_sage.portfolio.costs import CostModel
from market_sage.portfolio.risk import RiskSettings


@dataclass
class Holding:
    symbol: str
    sector: str | None
    market_value: float


@dataclass
class AllocationLine:
    symbol: str
    instrument_id: int
    sector: str | None
    quantity: int
    entry_price: float
    amount: float
    entry_costs: float
    stop: float
    target1: float
    target2: float
    loss_at_stop: float
    reward_risk: float
    expected_value: float
    probability_up: float | None
    horizon: str
    reason: str
    costs_verified: bool

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Allocation:
    capital: float
    mode: str
    lines: list[AllocationLine]
    reserve_cash: float
    total_invested: float
    total_entry_costs: float
    portfolio_loss_at_stops: float
    rejected: list[dict]
    settings_version: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "capital": self.capital,
            "mode": self.mode,
            "lines": [ln.to_dict() for ln in self.lines],
            "reserve_cash": self.reserve_cash,
            "total_invested": self.total_invested,
            "total_entry_costs": self.total_entry_costs,
            "portfolio_loss_at_stops": self.portfolio_loss_at_stops,
            "portfolio_loss_pct": self.portfolio_loss_at_stops / self.capital if self.capital else 0.0,
            "rejected": self.rejected,
            "settings_version": self.settings_version,
            "notes": self.notes,
        }


def risk_sized_quantity(risk_budget: float, entry: float, stop: float, costs: CostModel) -> int:
    """Largest quantity whose loss at stop (price move + round-trip costs incl. slippage) fits the budget."""
    lo, hi = 0, int(risk_budget // max(entry - stop, 0.01))
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if mid * (entry - stop) + costs.round_trip(entry, stop, mid) <= risk_budget:
            lo = mid
        else:
            hi = mid - 1
    return lo


def allocate(
    capital: float,
    recs: list[Recommendation],
    settings: RiskSettings,
    costs: CostModel,
    sectors: dict[int, str | None],
    returns: pd.DataFrame | None = None,
    holdings: list[Holding] | None = None,
    committed_capital: float = 0.0,
) -> Allocation:
    if capital <= 0 or not math.isfinite(capital):
        raise ValueError("capital must be a positive amount")
    holdings = holdings or []
    rejected: list[dict] = []
    notes = [
        "Advisory only — paper trading. No order is placed by MARKET SAGE.",
        "Equities carry risk of loss; stops may fill worse than planned on gaps.",
    ]
    if not costs.verified:
        notes.append("Cost estimates use an UNVERIFIED charge schedule (reconcile with a broker contract note).")
    buys = [r for r in recs if r.action == "BUY" and r.plan is not None]
    for r in recs:
        if r not in buys:
            rejected.append({"symbol": r.symbol, "reason": "; ".join(r.reasons) or "not a BUY"})
    buys.sort(key=lambda r: r.quality_score or 0.0, reverse=True)
    # ``committed_capital``: part of ``capital`` already invested (e.g. open paper positions of the same book)
    deployable = capital * (1 - settings.min_cash_reserve_pct) - committed_capital
    cash = deployable
    sector_val: dict[str, float] = {}
    for h in holdings:
        if h.sector:
            sector_val[h.sector] = sector_val.get(h.sector, 0.0) + h.market_value
    lines: list[AllocationLine] = []
    slots = settings.max_positions - len(holdings)
    for r in buys:
        p = r.plan
        assert p is not None
        if len(lines) >= slots:
            rejected.append(
                {"symbol": r.symbol, "reason": f"ranked lower; max {settings.max_positions} positions reached"}
            )
            continue
        entry = p.entry_high  # conservative: size at the top of the entry range
        sector = sectors.get(r.instrument_id)
        if returns is not None and lines and r.symbol in returns:
            corr = max(
                (returns[r.symbol].corr(returns[ln.symbol]) for ln in lines if ln.symbol in returns), default=0.0
            )
            if np.isfinite(corr) and corr > settings.max_pair_correlation:
                rejected.append({"symbol": r.symbol, "reason": f"correlation {corr:.2f} with a selected holding"})
                continue
        qty = risk_sized_quantity(capital * settings.risk_per_trade_pct, entry, p.stop, costs)
        caps = {
            "risk": qty,
            "position_cap": int(capital * settings.max_position_pct // entry),
            "liquidity": int(r.liquidity["adv_20d"] * settings.max_adv_participation),
            "cash": int(cash // (entry * 1.003)),
        }
        qty = min(caps.values())
        if sector:
            room = capital * settings.max_sector_pct - sector_val.get(sector, 0.0)
            qty = min(qty, int(max(room, 0) // entry))
        if qty < 1:
            binding = min(caps, key=lambda k: caps[k])
            rejected.append({"symbol": r.symbol, "reason": f"not affordable within limits (binding: {binding})"})
            continue
        buy_cost = costs.leg("buy", entry, qty).total
        rt_t1 = costs.round_trip(entry, p.target1, qty)
        gain_t1 = qty * (p.target1 - entry)
        if rt_t1 > 0.25 * gain_t1:
            rejected.append(
                {
                    "symbol": r.symbol,
                    "reason": f"costs ₹{rt_t1:.0f} exceed 25% of expected gain at "
                    f"Target 1 (₹{gain_t1:.0f}); position too small",
                }
            )
            continue
        loss = qty * (entry - p.stop) + costs.round_trip(entry, p.stop, qty)
        amount = qty * entry
        cash -= amount + buy_cost
        if sector:
            sector_val[sector] = sector_val.get(sector, 0.0) + amount
        lines.append(
            AllocationLine(
                r.symbol,
                r.instrument_id,
                sector,
                qty,
                round(entry, 2),
                round(amount, 2),
                round(buy_cost, 2),
                p.stop,
                p.target1,
                p.target2,
                round(loss, 2),
                p.reward_risk_t1,
                round((r.expected_value_per_share or 0.0) * qty, 2),
                (r.probabilities or {}).get("up"),
                f"{p.horizon_range[0]}-{p.horizon_range[1]} sessions",
                "; ".join(x for x in r.thesis["13_why_selected"] if x),
                costs.verified,
            )
        )
    invested = sum(ln.amount for ln in lines)
    entry_costs = sum(ln.entry_costs for ln in lines)
    if not lines:
        notes.append(
            "No opportunity met the validated-edge, risk and cost criteria — holding cash is the recommendation."
        )
    return Allocation(
        capital,
        settings.mode,
        lines,
        round(capital - invested - entry_costs, 2),
        round(invested, 2),
        round(entry_costs, 2),
        round(sum(ln.loss_at_stop for ln in lines), 2),
        rejected,
        settings.version,
        notes,
    )
