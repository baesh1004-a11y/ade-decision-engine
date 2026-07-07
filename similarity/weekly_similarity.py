from __future__ import annotations

from dataclasses import dataclass

from weekly.pattern import WeeklyPattern
from weekly.shape_similarity import WeeklyShape, WeeklyShapeSimilarityEngine


@dataclass(frozen=True)
class WeeklySimilarityResult:
    event_id: str
    weekly_similarity: float
    weekly_pattern: str


class WeeklySimilarityEngine:
    """First gate: weekly chart shape must be similar.

    Uses chart shape similarity when WeeklyShape is provided.
    Keeps WeeklyPattern compatibility for older callers.
    """

    def __init__(self, min_similarity: float = 0.0) -> None:
        self.min_similarity = min_similarity
        self.shape_engine = WeeklyShapeSimilarityEngine(weeks=26)

    def score(self, query: WeeklyPattern | WeeklyShape, target: WeeklyPattern | WeeklyShape) -> float:
        if isinstance(query, WeeklyShape) and isinstance(target, WeeklyShape):
            return self.shape_engine.similarity(query, target)
        return self._vector_similarity(query.vector, target.vector)

    def filter(
        self,
        query: WeeklyPattern | WeeklyShape,
        targets: list[tuple[str, WeeklyPattern | WeeklyShape]],
        top_n: int = 100,
    ) -> list[WeeklySimilarityResult]:
        results: list[WeeklySimilarityResult] = []
        for event_id, pattern in targets:
            score = self.score(query, pattern)
            if score >= self.min_similarity:
                pattern_name = getattr(pattern, "pattern", "WEEKLY_SHAPE")
                results.append(WeeklySimilarityResult(event_id=event_id, weekly_similarity=score, weekly_pattern=pattern_name))
        return sorted(results, key=lambda item: item.weekly_similarity, reverse=True)[:top_n]

    @staticmethod
    def _vector_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        distance = sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
        return round(100.0 / (1.0 + distance), 2)
