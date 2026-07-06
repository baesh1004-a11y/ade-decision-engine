from __future__ import annotations

from dataclasses import dataclass

from sto.layer_engine import STOLayers


@dataclass(frozen=True)
class STOSimilarityResult:
    event_id: str
    sto_similarity: float
    sto_structure: str


class STOSimilarityEngine:
    """Second gate: compare STO 3-layer only after weekly match."""

    def __init__(self, min_similarity: float = 0.0) -> None:
        self.min_similarity = min_similarity

    def score(self, query: STOLayers, target: STOLayers) -> float:
        structure_bonus = 8.0 if query.structure == target.structure else 0.0
        base = self._similarity(query.vector, target.vector)
        return round(min(100.0, base + structure_bonus), 2)

    def filter(self, query: STOLayers, targets: list[tuple[str, STOLayers]], top_n: int = 20) -> list[STOSimilarityResult]:
        results: list[STOSimilarityResult] = []
        for event_id, layers in targets:
            score = self.score(query, layers)
            if score >= self.min_similarity:
                results.append(STOSimilarityResult(event_id=event_id, sto_similarity=score, sto_structure=layers.structure))
        return sorted(results, key=lambda item: item.sto_similarity, reverse=True)[:top_n]

    @staticmethod
    def _similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        distance = sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
        return round(100.0 / (1.0 + distance), 2)
