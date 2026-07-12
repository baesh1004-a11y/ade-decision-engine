from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np


class ReplayVectorIndex:
    """Read normalized Replay vectors and rank event IDs by cosine similarity.

    All vectors are loaded once and cached in memory. Candidate filtering is done
    in Python so large Replay databases never hit SQLite's bind-variable limit.
    """

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._event_ids: list[str] | None = None
        self._matrix: np.ndarray | None = None
        self._index_by_id: dict[str, int] | None = None

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
        self._ensure_cache()
        if self._matrix is None or self._event_ids is None or self._index_by_id is None:
            return []

        query_index = self._index_by_id.get(query_event_id)
        if query_index is None:
            return []
        query = self._matrix[query_index]

        if candidate_event_ids:
            indices = np.fromiter(
                (
                    index
                    for event_id in candidate_event_ids
                    if event_id != query_event_id
                    for index in [self._index_by_id.get(event_id)]
                    if index is not None
                ),
                dtype=np.int64,
            )
        else:
            indices = np.arange(len(self._event_ids), dtype=np.int64)
            indices = indices[indices != query_index]

        if indices.size == 0:
            return []

        scores = self._matrix[indices] @ query
        top_n = min(max(1, int(limit)), int(indices.size))
        if top_n < indices.size:
            local_top = np.argpartition(scores, -top_n)[-top_n:]
        else:
            local_top = np.arange(indices.size)
        local_top = local_top[np.argsort(scores[local_top])[::-1]]

        ranked: list[tuple[str, float]] = []
        for local_index in local_top:
            matrix_index = int(indices[int(local_index)])
            score = float(scores[int(local_index)]) * 100.0
            ranked.append(
                (
                    self._event_ids[matrix_index],
                    round(max(-100.0, min(100.0, score)), 2),
                )
            )
        return ranked

    def _ensure_cache(self) -> None:
        if self._matrix is not None and self._event_ids is not None and self._index_by_id is not None:
            return

        try:
            rows = self.conn.execute(
                "SELECT event_id, vector_json FROM replay_event_vectors ORDER BY event_id"
            ).fetchall()
        except sqlite3.OperationalError:
            self._event_ids = []
            self._matrix = np.empty((0, 0), dtype=float)
            self._index_by_id = {}
            return

        event_ids: list[str] = []
        vectors: list[np.ndarray] = []
        expected_size: int | None = None
        for row in rows:
            vector = self._decode(row["vector_json"])
            if vector is None:
                continue
            if expected_size is None:
                expected_size = int(vector.size)
            if vector.size != expected_size:
                continue
            event_ids.append(str(row["event_id"]))
            vectors.append(vector)

        self._event_ids = event_ids
        self._index_by_id = {event_id: index for index, event_id in enumerate(event_ids)}
        if vectors:
            self._matrix = np.vstack(vectors)
        else:
            self._matrix = np.empty((0, 0), dtype=float)

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
