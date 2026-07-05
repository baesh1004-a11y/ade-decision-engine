from __future__ import annotations

from dataclasses import asdict, dataclass

from recommendation.models import RecommendationScore


@dataclass(frozen=True)
class PortfolioPosition:
    market: str
    ticker: str
    weight: float
    score: int
    action: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PortfolioEngine:
    """Convert ranked recommendations into capped portfolio weights."""

    def allocate(
        self,
        recommendations: list[RecommendationScore],
        max_positions: int = 5,
        max_weight: float = 0.30,
    ) -> list[PortfolioPosition]:
        eligible = [item for item in recommendations if item.action in {"STRONG_BUY_CANDIDATE", "BUY_CANDIDATE", "WATCHLIST"}]
        eligible = eligible[:max_positions]
        if not eligible:
            return []

        raw_total = sum(max(item.final_score, 1) for item in eligible)
        weights = [min(max_weight, item.final_score / raw_total) for item in eligible]
        weight_total = sum(weights)
        if weight_total <= 0:
            return []

        return [
            PortfolioPosition(
                market=item.market,
                ticker=item.ticker,
                weight=round(weight / weight_total, 4),
                score=item.final_score,
                action=item.action,
            )
            for item, weight in zip(eligible, weights)
        ]
