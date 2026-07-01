from __future__ import annotations

from collections import defaultdict

from learning_v2.models import RuleSample, RuleStatistics


class RuleEvaluator:
    """Evaluate rule performance from realized trade samples."""

    def evaluate(self, samples: list[RuleSample | dict]) -> list[RuleStatistics]:
        normalized = [self._normalize(item) for item in samples]
        fired = [sample for sample in normalized if sample.fired]
        grouped: dict[str, list[RuleSample]] = defaultdict(list)
        for sample in fired:
            grouped[sample.rule_name].append(sample)

        stats: list[RuleStatistics] = []
        for rule_name, items in grouped.items():
            returns = [float(item.realized_return) for item in items]
            wins = [r for r in returns if r > 0]
            losses = [r for r in returns if r < 0]
            sample_count = len(returns)
            win_rate = len(wins) / sample_count if sample_count else 0.0
            avg_return = sum(returns) / sample_count if sample_count else 0.0
            avg_win = sum(wins) / len(wins) if wins else 0.0
            avg_loss = sum(losses) / len(losses) if losses else 0.0
            gross_profit = sum(wins)
            gross_loss = abs(sum(losses))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
            expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss if sample_count else 0.0
            performance_score = self._score(win_rate, avg_return, profit_factor, expectancy, sample_count)
            stats.append(
                RuleStatistics(
                    rule_name=rule_name,
                    sample_count=sample_count,
                    win_rate=round(win_rate, 4),
                    avg_return=round(avg_return, 4),
                    avg_win=round(avg_win, 4),
                    avg_loss=round(avg_loss, 4),
                    profit_factor=round(profit_factor, 4),
                    expectancy=round(expectancy, 4),
                    performance_score=round(performance_score, 4),
                )
            )
        return sorted(stats, key=lambda item: item.performance_score, reverse=True)

    def _normalize(self, item: RuleSample | dict) -> RuleSample:
        if isinstance(item, RuleSample):
            return item
        return RuleSample(
            rule_name=str(item["rule_name"]),
            fired=bool(item.get("fired", True)),
            realized_return=float(item.get("realized_return", 0.0)),
            metadata=item.get("metadata", {}),
        )

    def _score(self, win_rate: float, avg_return: float, profit_factor: float, expectancy: float, sample_count: int) -> float:
        sample_factor = min(1.0, sample_count / 30.0)
        pf_component = min(2.0, profit_factor) / 2.0
        return max(0.0, min(1.0, (win_rate * 0.35 + max(-0.1, min(0.1, avg_return)) * 3.0 + pf_component * 0.25 + max(-0.1, min(0.1, expectancy)) * 2.0) * sample_factor))
