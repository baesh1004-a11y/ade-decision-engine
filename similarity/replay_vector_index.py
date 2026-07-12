from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np


class ReplayVectorIndex:
    """Read normalized Replay vectors and rank event IDs by cosine similarity."""

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def count(self) -> int:
        try:
            return int(self.conn.execute("SELECT COUNT(*) FROM replay_event_vectors").fetchone()[0])
        except sqlite3.OperationalError:
            return 0

    def rank_similar(
        self,
        query_event_id: str,
        candidate_event_ids: list[str] | None = None,
        limit: int = 500,
    ) -> list[tuple[str, float]]:
        query = self._load_vector(query_event_id)
        if query is None:
            return []

        sql = "SELECT event_id, vector_json FROM replay_event_vectors WHERE event_id<>?"
        params: list[object] = [query_event_id]
        if candidate_event_ids:
            placeholders = ",".join("?" for _ in candidate_event_ids)
            sql += f" AND event_id IN ({placeholders})"
            params.extend(candidate_event_ids)

        ranked: list[tuple[str, float]] = []
        for row in self.conn.execute(sql, params).fetchall():
            vector = self._decode(row["vector_json"])
            if vector is None or len(vector) != len(query):
                continue
            score = float(np.dot(query, vector)) * 100.0
            ranked.append((str(row["event_id"]), round(max(-100.0, min(100.0, score)), 2)))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[: max(1, int(limit))]

    def _load_vector(self, event_id: str) -> np.ndarray | None:
        try:
            row = self.conn.execute(
                "SELECT vector_json FROM replay_event_vectors WHERE event_id=?",
                (event_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        return self._decode(row["vector_json"])

    @staticmethod
    def _decode(value: object) -> np.ndarray | None:
        try:
            arr = np.asarray(json.loads(str(value)), dtype=float)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if arr.ndim != 1 or arr.size == 0 or not np.isfinite(arr).all():
            return None
        norm = float(np.linalg.norm(arr))
        if norm <= 0:
            return None
        return arr / norm
