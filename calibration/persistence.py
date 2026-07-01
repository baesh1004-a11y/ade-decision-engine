from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from calibration.models import CalibrationTable, ProbabilityObservation


class CalibrationRepository:
    """SQLite persistence for probability observations and calibration tables."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS probability_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                prediction_date TEXT NOT NULL,
                horizon TEXT NOT NULL,
                predicted_probability REAL NOT NULL,
                actual_outcome INTEGER NOT NULL,
                expected_return REAL NOT NULL,
                realized_return REAL NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS probability_calibration_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine_version TEXT NOT NULL,
                horizon TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                bins_json TEXT NOT NULL,
                global_bias REAL NOT NULL,
                brier_score REAL NOT NULL,
                reasons_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def save_observations(self, observations: list[ProbabilityObservation | dict[str, Any]]) -> int:
        count = 0
        for item in observations:
            obs = item if isinstance(item, ProbabilityObservation) else ProbabilityObservation(**item)
            self.conn.execute(
                """
                INSERT INTO probability_observations (
                    ticker, prediction_date, horizon, predicted_probability, actual_outcome,
                    expected_return, realized_return, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    obs.ticker,
                    obs.prediction_date,
                    obs.horizon,
                    float(obs.predicted_probability),
                    int(obs.actual_outcome),
                    float(obs.expected_return),
                    float(obs.realized_return),
                    json.dumps(obs.metadata or {}),
                ),
            )
            count += 1
        self.conn.commit()
        return count

    def fetch_observations(self, horizon: str = "20d") -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM probability_observations WHERE horizon = ? ORDER BY id",
            (horizon,),
        ).fetchall()
        return [dict(row) for row in rows]

    def save_calibration_table(self, table: CalibrationTable | dict[str, Any]) -> int:
        payload = table.to_dict() if hasattr(table, "to_dict") else dict(table)
        cursor = self.conn.execute(
            """
            INSERT INTO probability_calibration_tables (
                engine_version, horizon, sample_count, bins_json, global_bias, brier_score, reasons_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["engine_version"],
                payload["horizon"],
                int(payload["sample_count"]),
                json.dumps(payload.get("bins", [])),
                float(payload["global_bias"]),
                float(payload["brier_score"]),
                json.dumps(payload.get("reasons", [])),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def fetch_latest_calibration_table(self, horizon: str = "20d") -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM probability_calibration_tables WHERE horizon = ? ORDER BY id DESC LIMIT 1",
            (horizon,),
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        return {
            "engine_version": payload["engine_version"],
            "horizon": payload["horizon"],
            "sample_count": payload["sample_count"],
            "bins": json.loads(payload["bins_json"]),
            "global_bias": payload["global_bias"],
            "brier_score": payload["brier_score"],
            "reasons": json.loads(payload["reasons_json"]),
        }

    def close(self) -> None:
        self.conn.close()
