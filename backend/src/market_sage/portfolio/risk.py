"""Versioned risk settings (decision D7). Every recommendation records the version it used."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class RiskSettings:
    mode: str = "balanced"  # balanced | growth
    risk_per_trade_pct: float = 0.0075  # balanced 0.75%, growth 1.0% of capital lost at stop (incl. costs)
    max_positions: int = 5
    max_position_pct: float = 0.25  # balanced 25%, growth 30%
    max_sector_pct: float = 0.40
    daily_loss_limit_pct: float = 0.02
    weekly_drawdown_limit_pct: float = 0.05
    min_cash_reserve_pct: float = 0.10
    min_median_turnover: float = 5e7  # ₹5 crore 20-day median turnover
    max_adv_participation: float = 0.01  # position <= 1% of average daily volume
    min_price: float = 20.0
    min_reward_risk: float = 1.5  # to Target 1, net of costs
    min_p_up: float = 0.45  # calibrated probability of upper barrier first
    max_pair_correlation: float = 0.85

    @property
    def version(self) -> str:
        return "risk-" + hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:10]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["version"] = self.version
        return d


def settings_for_mode(mode: str, **overrides: float) -> RiskSettings:
    base = RiskSettings()
    if mode == "growth":
        base = replace(base, mode="growth", risk_per_trade_pct=0.01, max_position_pct=0.30)
    elif mode != "balanced":
        raise ValueError("mode must be 'balanced' or 'growth'")
    return replace(base, **overrides) if overrides else base  # type: ignore[arg-type]
