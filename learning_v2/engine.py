from __future__ import annotations

from learning_v2.evaluator import RuleEvaluator
from learning_v2.models import LearningUpdate, RuleSample
from learning_v2.optimizer import RuleWeightOptimizer


ENGINE_VERSION = "adaptive-learning-v2.0.0"


class AdaptiveLearningEngineV2:
    """Evaluate rule performance and produce updated rule weights."""

    def __init__(self) -> None:
        self.evaluator = RuleEvaluator()
        self.optimizer = RuleWeightOptimizer()

    def update(self, samples: list[RuleSample | dict], current_weights: dict[str, float] | None = None) -> LearningUpdate:
        statistics = self.evaluator.evaluate(samples)
        weights = self.optimizer.optimize(statistics, current_weights=current_weights)
        reasons = [
            f"Evaluated {len(samples)} rule samples",
            f"Generated {len(weights)} adaptive rule weights",
        ]
        return LearningUpdate(
            engine_version=ENGINE_VERSION,
            sample_count=len(samples),
            statistics=[item.to_dict() for item in statistics],
            weights=[item.to_dict() for item in weights],
            reasons=reasons,
        )

    def weight_map(self, update: LearningUpdate | dict) -> dict[str, float]:
        payload = update.to_dict() if hasattr(update, "to_dict") else dict(update)
        return {item["rule_name"]: float(item["weight"]) for item in payload.get("weights", [])}
