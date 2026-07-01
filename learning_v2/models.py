from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RuleSample:
    rule_name: str
    fired: bool
    realized_return: float
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuleStatistics:
    rule_name: str
    sample_count: int
    win_rate: float
    avg_return: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    expectancy: float
    performance_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuleWeight:
    rule_name: str
    weight: float
    previous_weight: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningUpdate:
    engine_version: str
    sample_count: int
    statistics: list[dict[str, Any]]
    weights: list[dict[str, Any]]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
