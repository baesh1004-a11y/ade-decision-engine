from __future__ import annotations

from learning_v2.models import RuleStatistics, RuleWeight


class RuleWeightOptimizer:
    """Convert rule statistics into bounded rule weights."""

    def __init__(self, min_weight: float = 0.5, max_weight: float = 1.5, learning_rate: float = 0.25) -> None:
        if min_weight <= 0 or max_weight <= min_weight:
            raise ValueError("invalid weight bounds")
        if learning_rate <= 0 or learning_rate > 1:
            raise ValueError("learning_rate must be between 0 and 1")
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.learning_rate = learning_rate

    def optimize(
        self,
        statistics: list[RuleStatistics | dict],
        current_weights: dict[str, float] | None = None,
    ) -> list[RuleWeight]:
        current_weights = current_weights or {}
        weights: list[RuleWeight] = []
        for item in statistics:
            stat = self._normalize(item)
            previous = float(current_weights.get(stat.rule_name, 1.0))
            target = self._target_weight(stat.performance_score)
            new_weight = previous + (target - previous) * self.learning_rate
            new_weight = max(self.min_weight, min(self.max_weight, new_weight))
            weights.append(
                RuleWeight(
                    rule_name=stat.rule_name,
                    weight=round(new_weight, 4),
                    previous_weight=round(previous, 4),
                    reason=self._reason(stat, previous, new_weight),
                )
            )
        return weights

    def _normalize(self, item: RuleStatistics | dict) -> RuleStatistics:
        if isinstance(item, RuleStatistics):
            return item
        return RuleStatistics(
            rule_name=str(item["rule_name"]),
            sample_count=int(item["sample_count"]),
            win_rate=float(item["win_rate"]),
            avg_return=float(item["avg_return"]),
            avg_win=float(item.get("avg_win", 0.0)),
            avg_loss=float(item.get("avg_loss", 0.0)),
            profit_factor=float(item["profit_factor"]),
            expectancy=float(item["expectancy"]),
            performance_score=float(item["performance_score"]),
        )

    def _target_weight(self, score: float) -> float:
        # score 0.5 => weight 1.0, score 1.0 => max, score 0.0 => min
        return self.min_weight + (self.max_weight - self.min_weight) * max(0.0, min(1.0, score))

    def _reason(self, stat: RuleStatistics, previous: float, new: float) -> str:
        direction = "increased" if new > previous else "decreased" if new < previous else "unchanged"
        return (
            f"Rule {stat.rule_name} weight {direction}: "
            f"score={stat.performance_score:.2f}, win_rate={stat.win_rate:.2%}, "
            f"profit_factor={stat.profit_factor:.2f}, samples={stat.sample_count}"
        )
