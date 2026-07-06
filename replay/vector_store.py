from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class ReplayVectorStore:
    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE IF NOT EXISTS replay_event_vectors (event_id TEXT PRIMARY KEY, vector_json TEXT NOT NULL, feature_names_json TEXT NOT NULL, labels_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        self.conn.commit()

    def save(self, event_id: str, vector: list[float], feature_names: list[str], labels: list[str]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO replay_event_vectors (event_id, vector_json, feature_names_json, labels_json) VALUES (?, ?, ?, ?)",
            (event_id, json.dumps(vector), json.dumps(feature_names), json.dumps(labels)),
        )

    def all(self) -> list[dict[str, object]]:
        rows = self.conn.execute("SELECT event_id, vector_json, feature_names_json, labels_json FROM replay_event_vectors").fetchall()
        return [
            {
                "event_id": row["event_id"],
                "vector": json.loads(row["vector_json"]),
                "feature_names": json.loads(row["feature_names_json"]),
                "labels": json.loads(row["labels_json"]),
            }
            for row in rows
        ]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS c FROM replay_event_vectors").fetchone()["c"])

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
