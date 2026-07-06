from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class DataProvenanceSummary:
    historical_source: str
    realtime_source: str
    database_source: str
    last_updated: str | None
    total_symbols: int
    total_rows: int
    quality_label: str


class DataProvenanceStore:
    """Track where ADE data came from and when it was refreshed."""

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_collection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                historical_source TEXT NOT NULL,
                realtime_source TEXT NOT NULL,
                database_source TEXT NOT NULL,
                target_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                fail_count INTEGER NOT NULL DEFAULT 0,
                total_rows INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'RUNNING'
            )
            """
        )
        self.conn.commit()

    def start_run(self, historical_source: str = "FDR", realtime_source: str = "KIS", database_source: str = "SQLite DataHub", target_count: int = 0) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.execute(
            """
            INSERT INTO data_collection_runs (started_at, historical_source, realtime_source, database_source, target_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (now, historical_source, realtime_source, database_source, target_count),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, success_count: int, fail_count: int, total_rows: int, status: str = "DONE") -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            UPDATE data_collection_runs
            SET finished_at=?, success_count=?, fail_count=?, total_rows=?, status=?
            WHERE id=?
            """,
            (now, success_count, fail_count, total_rows, status, run_id),
        )
        self.conn.commit()

    def summary(self) -> DataProvenanceSummary:
        run = self.conn.execute(
            """
            SELECT * FROM data_collection_runs
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        total_symbols = self.conn.execute("SELECT COUNT(DISTINCT market || ':' || ticker) AS cnt FROM price_bars").fetchone()["cnt"]
        total_rows = self.conn.execute("SELECT COUNT(*) AS cnt FROM price_bars").fetchone()["cnt"]
        if run is None:
            return DataProvenanceSummary("FDR", "KIS", "SQLite DataHub", None, int(total_symbols), int(total_rows), "UNKNOWN")
        success = int(run["success_count"] or 0)
        fail = int(run["fail_count"] or 0)
        quality = "★★★★★" if fail == 0 and success > 0 else "★★★★☆" if fail <= max(3, success * 0.03) else "★★★☆☆"
        return DataProvenanceSummary(
            historical_source=str(run["historical_source"]),
            realtime_source=str(run["realtime_source"]),
            database_source=str(run["database_source"]),
            last_updated=str(run["finished_at"] or run["started_at"]),
            total_symbols=int(total_symbols),
            total_rows=int(total_rows),
            quality_label=quality,
        )

    def close(self) -> None:
        self.conn.close()
