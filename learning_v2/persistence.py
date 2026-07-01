from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class LearningV2Repository:
    """SQLite persistence for adaptive rule statistics and weights."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rule_statistics_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                avg_return REAL NOT NULL,
                avg_win REAL NOT NULL,
                avg_loss REAL NOT NULL,
                profit_factor REAL NOT NULL,
                expectancy REAL NOT NULL,
                performance_score REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rule_weights_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT NOT NULL,
                weight REAL NOT NULL,
                previous_weight REAL NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS learning_updates_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine_version TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                statistics_json TEXT NOT NULL,
                weights_json TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def save_update(self, update: dict[str, Any]) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO learning_updates_v2 (
                engine_version, sample_count, statistics_json, weights_json, reasons_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                update["engine_version"],
                int(update["sample_count"]),
                json.dumps(update.get("statistics", [])),
                json.dumps(update.get("weights", [])),
                json.dumps(update.get("reasons", [])),
            ),
        )
        update_id = int(cursor.lastrowid)
        for stat in update.get("statistics", []):
            self.conn.execute(
                """
                INSERT INTO rule_statistics_v2 (
                    rule_name, sample_count, win_rate, avg_return, avg_win, avg_loss,
                    profit_factor, expectancy, performance_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stat["rule_name"], int(stat["sample_count"]), float(stat["win_rate"]),
                    float(stat["avg_return"]), float(stat["avg_win"]), float(stat["avg_loss"]),
                    float(stat["profit_factor"]), float(stat["expectancy"]), float(stat["performance_score"]),
                ),
            )
        for weight in update.get("weights", []):
            self.conn.execute(
                """
                INSERT INTO rule_weights_v2 (rule_name, weight, previous_weight, reason)
                VALUES (?, ?, ?, ?)
                """,
                (weight["rule_name"], float(weight["weight"]), float(weight["previous_weight"]), weight["reason"]),
            )
        self.conn.commit()
        return update_id

    def fetch_latest_weights(self) -> dict[str, float]:
        rows = self.conn.execute(
            """
            SELECT rw.rule_name, rw.weight
            FROM rule_weights_v2 rw
            INNER JOIN (
                SELECT rule_name, MAX(id) AS max_id
                FROM rule_weights_v2
                GROUP BY rule_name
            ) latest ON rw.rule_name = latest.rule_name AND rw.id = latest.max_id
            """
        ).fetchall()
        return {row["rule_name"]: float(row["weight"]) for row in rows}

    def close(self) -> None:
        self.conn.close()
