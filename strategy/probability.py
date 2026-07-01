from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ENGINE_VERSION = "probability-engine-v1.0.0"


@dataclass(frozen=True)
class ProbabilityDecision:
    engine_version: str
    ticker: str
    horizon: str
    upside_probability: float
    downside_probability: float
    expected_return: float
    expected_mdd: float
    risk_reward: float
    confidence: float
    recommendation: str
    risk_flags: list[str]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProbabilityEngine:
    """Convert Pattern Context evidence into investment probabilities.

    v1.0 is a transparent probability layer. It uses pattern-context similarity,
    top-k win rate, expected return, and matched-sample drawdown proxy to produce
    upside/downside probability, risk-reward, confidence, and recommendation.
    """

    def __init__(self, horizon_days: int = 20) -> None:
        if horizon_days <= 0:
            raise ValueError("horizon_days must be greater than zero")
        self.horizon_days = horizon_days

    def evaluate(self, pattern_context: dict[str, Any]) -> ProbabilityDecision:
        ticker = str(pattern_context.get("ticker", "UNKNOWN"))
        horizon = f"{self.horizon_days}d"
        return_key = f"return_{self.horizon_days}d"
        win_rate_key = f"win_rate_{self.horizon_days}d"

        expected_return = float(pattern_context.get("expected_returns", {}).get(return_key, 0.0))
        win_rate = float(pattern_context.get("win_rates", {}).get(win_rate_key, 0.0))
        combined_similarity = float(pattern_context.get("combined_similarity", 0.0))
        context_similarity = float(pattern_context.get("context_similarity", 0.0))
        pattern_similarity = float(pattern_context.get("pattern_similarity", 0.0))
        risk_flags = list(pattern_context.get("risk_flags", []))

        expected_mdd = self._estimate_mdd(pattern_context, expected_return)
        risk_reward = self._risk_reward(expected_return, expected_mdd)
        confidence = self._confidence(combined_similarity, context_similarity, pattern_similarity, len(risk_flags))
        upside_probability = self._upside_probability(win_rate, expected_return, combined_similarity, confidence)
        downside_probability = max(0.0, min(1.0, 1.0 - upside_probability))
        flags = self._risk_flags(risk_flags, upside_probability, expected_return, expected_mdd, risk_reward, confidence)
        recommendation = self._recommendation(upside_probability, expected_return, risk_reward, confidence, flags)
        reasons = self._reasons(upside_probability, expected_return, expected_mdd, risk_reward, confidence, recommendation, flags)

        return ProbabilityDecision(
            engine_version=ENGINE_VERSION,
            ticker=ticker,
            horizon=horizon,
            upside_probability=round(upside_probability, 4),
            downside_probability=round(downside_probability, 4),
            expected_return=round(expected_return, 4),
            expected_mdd=round(expected_mdd, 4),
            risk_reward=round(risk_reward, 4),
            confidence=round(confidence, 4),
            recommendation=recommendation,
            risk_flags=flags,
            reasons=reasons,
        )

    def _estimate_mdd(self, pattern_context: dict[str, Any], expected_return: float) -> float:
        matches = pattern_context.get("pattern", {}).get("matches", [])
        returns = []
        key = f"return_{self.horizon_days}d"
        for match in matches:
            value = match.get("forward_returns", {}).get(key)
            if value is not None:
                returns.append(float(value))
        if not returns:
            return min(-0.02, expected_return * -0.5) if expected_return > 0 else min(-0.03, expected_return)
        downside = [ret for ret in returns if ret < 0]
        if downside:
            return float(sum(downside) / len(downside))
        return -max(0.01, abs(min(returns)) * 0.5)

    def _risk_reward(self, expected_return: float, expected_mdd: float) -> float:
        risk = abs(expected_mdd)
        if risk <= 0:
            return 0.0
        return expected_return / risk

    def _confidence(self, combined: float, context: float, pattern: float, risk_count: int) -> float:
        raw = combined * 0.55 + context * 0.25 + pattern * 0.20
        penalty = min(0.25, risk_count * 0.05)
        return max(0.0, min(1.0, raw - penalty))

    def _upside_probability(self, win_rate: float, expected_return: float, combined: float, confidence: float) -> float:
        expected_component = max(-0.2, min(0.2, expected_return))
        raw = win_rate * 0.55 + combined * 0.25 + confidence * 0.15 + (0.5 + expected_component * 2.0) * 0.05
        return max(0.0, min(1.0, raw))

    def _risk_flags(
        self,
        inherited: list[str],
        upside_probability: float,
        expected_return: float,
        expected_mdd: float,
        risk_reward: float,
        confidence: float,
    ) -> list[str]:
        flags = list(inherited)
        if upside_probability < 0.50:
            flags.append("Upside probability below 50%")
        if expected_return < 0:
            flags.append("Negative expected return")
        if expected_mdd <= -0.08:
            flags.append("Expected drawdown is high")
        if risk_reward < 1.0:
            flags.append("Risk reward below 1.0")
        if confidence < 0.60:
            flags.append("Low probability confidence")
        return flags

    def _recommendation(
        self,
        upside_probability: float,
        expected_return: float,
        risk_reward: float,
        confidence: float,
        flags: list[str],
    ) -> str:
        if "Negative expected return" in flags or upside_probability < 0.45:
            return "AVOID"
        if upside_probability >= 0.70 and expected_return >= 0.05 and risk_reward >= 2.0 and confidence >= 0.75:
            return "STRONG_BUY"
        if upside_probability >= 0.60 and expected_return > 0 and risk_reward >= 1.2 and confidence >= 0.65:
            return "BUY"
        if upside_probability >= 0.52 and expected_return > 0:
            return "WATCH"
        return "AVOID"

    def _reasons(
        self,
        upside_probability: float,
        expected_return: float,
        expected_mdd: float,
        risk_reward: float,
        confidence: float,
        recommendation: str,
        flags: list[str],
    ) -> list[str]:
        reasons = [
            f"Upside probability is {upside_probability:.2%}",
            f"Expected return is {expected_return:.2%}",
            f"Expected MDD proxy is {expected_mdd:.2%}",
            f"Risk reward is {risk_reward:.2f}",
            f"Probability confidence is {confidence:.2%}",
            f"Recommendation is {recommendation}",
        ]
        if flags:
            reasons.append("Probability evidence requires caution")
        return reasons


def evaluate_probability(pattern_context: dict[str, Any], horizon_days: int = 20) -> dict[str, Any]:
    return ProbabilityEngine(horizon_days=horizon_days).evaluate(pattern_context).to_dict()
