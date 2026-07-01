from __future__ import annotations

from typing import Any

import pandas as pd

from candidate_rules.models import RuleScore, RuleScoreDecision


ENGINE_VERSION = "candidate-rule-score-v1.0.0"


class CandidateRuleScoreEngine:
    """Explicit rule-based candidate score engine.

    This decomposes the candidate score into auditable rule scores so adaptive
    learning can adjust rule weights directly instead of relying on free-text
    reason matching.
    """

    def evaluate(
        self,
        df: pd.DataFrame,
        pattern_context: dict[str, Any] | None = None,
        probability: dict[str, Any] | None = None,
        rule_weights: dict[str, float] | None = None,
    ) -> RuleScoreDecision:
        rule_weights = rule_weights or {}
        rules = [
            self._trend_rule(df, rule_weights),
            self._momentum_rule(df, rule_weights),
            self._volume_rule(df, rule_weights),
            self._pattern_rule(pattern_context or {}, rule_weights),
            self._probability_rule(probability or {}, rule_weights),
            self._volatility_rule(df, rule_weights),
        ]
        total = round(sum(rule.weighted_score() for rule in rules))
        total = max(0, min(100, int(total)))
        risk_flags = [rule.reason for rule in rules if rule.score <= rule.max_score * 0.25]
        confidence = max(0.0, min(1.0, total / 100.0))
        return RuleScoreDecision(
            engine_version=ENGINE_VERSION,
            total_score=total,
            grade=self._grade(total),
            action=self._action(total, risk_flags),
            confidence=round(confidence, 4),
            rule_scores={rule.rule_name: round(rule.score, 4) for rule in rules},
            weighted_rule_scores={rule.rule_name: round(rule.weighted_score(), 4) for rule in rules},
            rules=[rule.to_dict() for rule in rules],
            reasons=[rule.reason for rule in rules],
            risk_flags=risk_flags,
        )

    def _trend_rule(self, df: pd.DataFrame, weights: dict[str, float]) -> RuleScore:
        row = df.iloc[-1]
        close = float(row.get("Close", 0.0))
        ma20 = float(row.get("MA20", close)) if not pd.isna(row.get("MA20", close)) else close
        ma60 = float(row.get("MA60", ma20)) if not pd.isna(row.get("MA60", ma20)) else ma20
        score = 20.0 if close > ma20 > ma60 else 12.0 if close > ma20 else 5.0
        return RuleScore("trend", score, 20.0, float(weights.get("trend", 1.0)), f"Trend rule score {score}/20")

    def _momentum_rule(self, df: pd.DataFrame, weights: dict[str, float]) -> RuleScore:
        if len(df) < 21:
            score = 5.0
        else:
            ret20 = float(df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1.0)
            score = 15.0 if ret20 > 0.08 else 10.0 if ret20 > 0.02 else 4.0
        return RuleScore("momentum", score, 15.0, float(weights.get("momentum", 1.0)), f"Momentum rule score {score}/15")

    def _volume_rule(self, df: pd.DataFrame, weights: dict[str, float]) -> RuleScore:
        row = df.iloc[-1]
        ratio = row.get("VOL20_RATIO", 1.0)
        ratio = 1.0 if pd.isna(ratio) else float(ratio)
        score = 15.0 if ratio >= 2.0 else 10.0 if ratio >= 1.2 else 5.0
        return RuleScore("volume", score, 15.0, float(weights.get("volume", 1.0)), f"Volume rule score {score}/15")

    def _pattern_rule(self, pattern_context: dict[str, Any], weights: dict[str, float]) -> RuleScore:
        similarity = float(pattern_context.get("combined_similarity", pattern_context.get("pattern_similarity", 0.0)))
        score = 20.0 if similarity >= 0.8 else 15.0 if similarity >= 0.7 else 8.0 if similarity > 0 else 5.0
        return RuleScore("pattern", score, 20.0, float(weights.get("pattern", 1.0)), f"Pattern rule score {score}/20")

    def _probability_rule(self, probability: dict[str, Any], weights: dict[str, float]) -> RuleScore:
        upside = float(probability.get("upside_probability", 0.0))
        expected = float(probability.get("expected_return", 0.0))
        score = 20.0 if upside >= 0.7 and expected > 0 else 15.0 if upside >= 0.6 else 8.0 if upside >= 0.5 else 3.0
        return RuleScore("probability", score, 20.0, float(weights.get("probability", 1.0)), f"Probability rule score {score}/20")

    def _volatility_rule(self, df: pd.DataFrame, weights: dict[str, float]) -> RuleScore:
        returns = df["Close"].astype(float).pct_change().tail(20).dropna()
        vol = float(returns.std()) if not returns.empty else 0.0
        score = 10.0 if vol <= 0.03 else 6.0 if vol <= 0.05 else 2.0
        return RuleScore("volatility", score, 10.0, float(weights.get("volatility", 1.0)), f"Volatility rule score {score}/10")

    def _grade(self, score: int) -> str:
        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "C"
        if score >= 40:
            return "D"
        return "F"

    def _action(self, score: int, risk_flags: list[str]) -> str:
        if score >= 85 and len(risk_flags) <= 1:
            return "BUY_CANDIDATE"
        if score >= 70:
            return "WATCHLIST"
        if score >= 55:
            return "NEUTRAL"
        return "REJECT"
