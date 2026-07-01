from __future__ import annotations

from typing import Protocol

from pattern.memory import PatternMemoryMatch, PatternMemoryRecord


class MemoryRepository(Protocol):
    """Repository interface for ADE pattern memory backends.

    SQLite, FAISS, and Qdrant backends should implement this protocol so the
    pipeline can remain backend-agnostic.
    """

    def initialize(self) -> None: ...

    def upsert(self, record: PatternMemoryRecord) -> None: ...

    def bulk_upsert(self, records) -> int: ...

    def count(self) -> int: ...

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        market: str | None = None,
        ticker: str | None = None,
        exclude_trade_date: str | None = None,
    ) -> list[PatternMemoryMatch]: ...
