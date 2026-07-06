from __future__ import annotations

from dataclasses import dataclass

from replay.vector_store import ReplayVectorStore
from state.vector import ADEStateVectorEngine


@dataclass(frozen=True)
class StateVectorMatch:
    event_id: str
    similarity: float
    labels: list[str]


class StateVectorSearch:
    def __init__(self, db_path: str = "datahub/market.db") -> None:
        self.store = ReplayVectorStore(db_path)
        self.vector_engine = ADEStateVectorEngine()

    def close(self) -> None:
        self.store.close()

    def search(self, vector: list[float], top_n: int = 30) -> list[StateVectorMatch]:
        result: list[StateVectorMatch] = []
        for item in self.store.all():
            score = self.vector_engine.similarity(vector, item["vector"])
            result.append(StateVectorMatch(str(item["event_id"]), score, list(item["labels"])))
        return sorted(result, key=lambda x: x.similarity, reverse=True)[:top_n]
