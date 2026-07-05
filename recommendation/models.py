from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RecommendationInput:
    market: str
    ticker: str
    name: str | None
    market_data: Any
    sector: str | None = None


@dataclass(frozen=True)
class RecommendationScore:
    market: str
    ticker: str
    name: str | None
    sector: str | None
    final_score: int
    grade: str
    action: str
    confidence: float
    components: dict[str, int]
    reasons: list[str]
    risk_flags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecommendationReport:
    title: str
    total_universe: int
    selected_count: int
    recommendations: list[RecommendationScore]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "total_universe": self.total_universe,
            "selected_count": self.selected_count,
            "recommendations": [item.to_dict() for item in self.recommendations],
        }
