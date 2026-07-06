from __future__ import annotations

from dataclasses import dataclass

from similarity.replay_candidate import ReplayCandidate
from weekly.pattern import WeeklyPattern


@dataclass(frozen=True)
class WeeklySimilarityResult:
    event_id: str
    weekly_similarity: float
    weekly_pattern: str


class WeeklySimilarityEngine:
    """First gate: weekly chart structure must be similar."""

    def __init__(self, min_similarity: float = 0.0) -> None:
        self.min_similarity = min_similarity

    def score(self, query: WeeklyPattern, target: WeeklyPattern) -> float:
        return self._similarity(query.vector, target.vector)

    def filter(self, query: WeeklyPattern, targets: list[tuple[str, WeeklyPattern]], top_n: int = 100) -> list[WeeklySimilarityResult]:
        results: list[WeeklySimilarityResult] = []
        for event_id, pattern in targets:
            score = self.score(query, pattern)
            if score >= self.min_similarity:
                results.append(WeeklySimilarityResult(event_id=event_id, weekly_similarity=score, weekly_pattern=pattern.pattern))
        return sorted(results, key=lambda item: item.weekly_similarity, reverse=True)[:top_n]

    @staticmethod
    def _similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        distance = sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
        return round(100.0 / (1.0 + distance), 2)
