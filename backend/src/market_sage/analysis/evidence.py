"""Typed evidence: keeps facts, inferences, model estimates and unknowns separate (spec requirement)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EvidenceKind = Literal["fact", "inference", "estimate", "unknown"]
Stance = Literal["bullish", "bearish", "neutral"]


@dataclass(frozen=True)
class Evidence:
    category: str  # structure | indicators | patterns | volume | context | fundamentals | analogues | risk
    kind: EvidenceKind
    stance: str  # bullish | bearish | neutral (validated)
    statement: str
    value: Any = None
    method: str = ""
    as_of: str | None = None
    weight: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.stance not in ("bullish", "bearish", "neutral"):
            raise ValueError(f"invalid stance {self.stance}")
        if self.kind not in ("fact", "inference", "estimate", "unknown"):
            raise ValueError(f"invalid evidence kind {self.kind}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def tally(evidence: list[Evidence]) -> dict[str, float]:
    out = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    for e in evidence:
        if e.kind != "unknown":
            out[e.stance] += e.weight
    return out
