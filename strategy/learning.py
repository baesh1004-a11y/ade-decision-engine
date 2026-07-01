from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any


ENGINE_VERSION = "learning-engine-v1.0.0"


@dataclass(frozen=True)
class LearningSample:
    engine: str
    rule: str
    action: str
    expected_return: float
    realized_return: float
    holding_days: int = 0
    risk_level: str = "LOW"


@dataclass(frozen=True)
class RuleLearningResult:
    engine: str
    rule: str
    sample_count: int
    win_rate: float
    avg_return: float
    avg_alpha: float
    recommendation: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class LearningDecision:
    engine_version: str
    sample_count: int
    learning_score: int
    action: str
    recommendations: list[dict[str, Any]]
    weak_rules: list[str]
    strong_rules: list[str]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LearningEngine:
    """ADE Learning Engine v1.0.

    This engine performs conservative rule-level feedback analysis. It does not
    auto-change production rules. It recommends whether a rule should be kept,
    boosted, reduced, or reviewed after enough samples.
    """

    def __init__(
        self,
        min_samples: int = 5,
        strong_win_rate: float = 0.60,
        weak_win_rate: float = 0.40,
        min_avg_return: float = 0.0,
    ) -> None:
        self.min_samples = min_samples
        self.strong_win_rate = strong_win_rate
        self.weak_win_rate = weak_win_rate
        self.min_avg_return = min_avg_return

    def evaluate(self, samples: list[LearningSample | dict[str, Any]]) -> LearningDecision:
        normalized = [self._normalize(sample) for sample in samples]
        if not normalized:
            raise ValueError("LearningEngine requires at least one sample")

        grouped: dict[tuple[str, str], list[LearningSample]] = {}
        for sample in normalized:
            self._validate(sample)
            grouped.setdefault((sample.engine, sample.rule), []).append(sample)

        results = [self._evaluate_rule(engine, rule, rule_samples) for (engine, rule), rule_samples in grouped.items()]
        weak_rules = [f"{r.engine}:{r.rule}" for r in results if r.recommendation in {"REDUCE_WEIGHT", "REVIEW_OFF"}]
        strong_rules = [f"{r.engine}:{r.rule}" for r in results if r.recommendation == "BOOST_WEIGHT"]
        score = self._learning_score(results)
        action = self._action(score, weak_rules, strong_rules)

        reasons = []
        if weak_rules:
            reasons.append("Some rules show weak realized performance")
        if strong_rules:
            reasons.append("Some rules show persistent positive performance")
        if not reasons:
            reasons.append("No urgent learning adjustment required")

        return LearningDecision(
            engine_version=ENGINE_VERSION,
            sample_count=len(normalized),
            learning_score=score,
            action=action,
            recommendations=[asdict(result) for result in sorted(results, key=lambda r: (r.engine, r.rule))],
            weak_rules=weak_rules,
            strong_rules=strong_rules,
            reasons=reasons,
        )

    def _normalize(self, sample: LearningSample | dict[str, Any]) -> LearningSample:
        if isinstance(sample, LearningSample):
            return sample
        return LearningSample(
            engine=str(sample["engine"]),
            rule=str(sample["rule"]),
            action=str(sample.get("action", "UNKNOWN")),
            expected_return=float(sample.get("expected_return", 0.0)),
            realized_return=float(sample["realized_return"]),
            holding_days=int(sample.get("holding_days", 0)),
            risk_level=str(sample.get("risk_level", "LOW")),
        )

    def _validate(self, sample: LearningSample) -> None:
        if not sample.engine:
            raise ValueError("engine is required")
        if not sample.rule:
            raise ValueError("rule is required")
        if sample.holding_days < 0:
            raise ValueError("holding_days cannot be negative")

    def _evaluate_rule(self, engine: str, rule: str, samples: list[LearningSample]) -> RuleLearningResult:
        returns = [sample.realized_return for sample in samples]
        alphas = [sample.realized_return - sample.expected_return for sample in samples]
        wins = [ret > 0 for ret in returns]
        win_rate = sum(wins) / len(wins)
        avg_return = mean(returns)
        avg_alpha = mean(alphas)
        confidence = min(1.0, len(samples) / max(self.min_samples, 1))

        if len(samples) < self.min_samples:
            recommendation = "KEEP_COLLECTING"
            reason = "Insufficient sample size"
        elif win_rate >= self.strong_win_rate and avg_return > self.min_avg_return and avg_alpha >= 0:
            recommendation = "BOOST_WEIGHT"
            reason = "Rule has strong win rate and non-negative alpha"
        elif win_rate < self.weak_win_rate and avg_return < 0:
            recommendation = "REVIEW_OFF"
            reason = "Rule has weak win rate and negative average return"
        elif avg_alpha < -0.01:
            recommendation = "REDUCE_WEIGHT"
            reason = "Rule underperforms expected return by more than 1%"
        else:
            recommendation = "KEEP_WEIGHT"
            reason = "Rule performance is acceptable"

        return RuleLearningResult(
            engine=engine,
            rule=rule,
            sample_count=len(samples),
            win_rate=round(win_rate, 4),
            avg_return=round(avg_return, 4),
            avg_alpha=round(avg_alpha, 4),
            recommendation=recommendation,
            confidence=round(confidence, 4),
            reason=reason,
        )

    def _learning_score(self, results: list[RuleLearningResult]) -> int:
        score = 75
        for result in results:
            if result.recommendation == "BOOST_WEIGHT":
                score += 5
            elif result.recommendation == "KEEP_COLLECTING":
                score -= 2
            elif result.recommendation == "REDUCE_WEIGHT":
                score -= 10
            elif result.recommendation == "REVIEW_OFF":
                score -= 18
        return max(0, min(100, score))

    def _action(self, score: int, weak_rules: list[str], strong_rules: list[str]) -> str:
        if weak_rules:
            return "REVIEW_RULES"
        if strong_rules and score >= 80:
            return "APPLY_CONSERVATIVE_BOOST"
        return "KEEP_CURRENT_RULES"


def evaluate_learning(samples: list[LearningSample | dict[str, Any]]) -> dict[str, Any]:
    return LearningEngine().evaluate(samples).to_dict()
