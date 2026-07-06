from __future__ import annotations

from dataclasses import dataclass

from cache.vector_cache import VectorCache, VectorRecord


@dataclass(frozen=True)
class VectorSearchMatch:
    market: str
    ticker: str
    trade_date: str
    similarity: float


class VectorIndex:
    """Small dependency-free vector search for ADE pattern vectors."""

    def __init__(self, records: list[VectorRecord]) -> None:
        self.records = records

    @classmethod
    def from_cache(cls, db_path: str = "datahub/market.db") -> "VectorIndex":
        cache = VectorCache(db_path)
        try:
            return cls(cache.fetch_all())
        finally:
            cache.close()

    def search(self, query: list[float], top_n: int = 100) -> list[VectorSearchMatch]:
        scored: list[VectorSearchMatch] = []
        for record in self.records:
            scored.append(
                VectorSearchMatch(
                    market=record.market,
                    ticker=record.ticker,
                    trade_date=record.trade_date,
                    similarity=round(self._cosine(query, record.vector) * 100, 2),
                )
            )
        return sorted(scored, key=lambda item: item.similarity, reverse=True)[:top_n]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (norm_a * norm_b)))
