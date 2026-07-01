from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuleScore:
    rule_name: str
    score: float
    max_score: float
    weight: float
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def weighted_score(self) -> float:
        return self.score * self.weight

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["weighted_score"] = round(self.weighted_score(), 4)
        return payload


@dataclass(frozen=True)
class RuleScoreDecision:
    engine_version: str
    total_score: int
    grade: str
    action: str
    confidence: float
    rule_scores: dict[str, float]
    weighted_rule_scores: dict[str, float]
    rules: list[dict[str, Any]]
    reasons: list[str]
    risk_flags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
