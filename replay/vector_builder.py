from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np


VECTOR_VERSION = "replay-flow-v1"


@dataclass(frozen=True)
class ReplayVectorBuildStats:
    scanned_events: int
    upserted_vectors: int
    skipped_events: int
    total_vectors: int


class ReplayEventVectorBuilder:
    """Create compact numeric vectors from Replay event flows.

    The vectors are used only as a fast coarse pre-filter. Final matching still
    uses the existing weekly-shape and STO sliding matcher.
    """

    REQUIRED_COLUMNS = {
        "event_id",
        "ade_version",
        "market",
        "ticker",
        "event_date",
        "vector_version",
        "vector_json",
        "flow_days",
        "return_5d",
        "return_20d",
        "return_last",
        "volatility",
        "max_drawdown",
        "volume_ratio",
        "sto_bull_ratio",
        "ma_bull_ratio",
        "weekly_high_ratio",
        "created_at",
        "updated_at",
    }

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        existing = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(replay_event_vectors)").fetchall()
        }
        if existing and not self.REQUIRED_COLUMNS.issubset(existing):
            self.conn.execute("DROP TABLE replay_event_vectors")

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS replay_event_vectors (
                event_id TEXT PRIMARY KEY,
                ade_version TEXT NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                event_date TEXT NOT NULL,
                vector_version TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                flow_days INTEGER NOT NULL,
                return_5d REAL NOT NULL,
                return_20d REAL NOT NULL,
                return_last REAL NOT NULL,
                volatility REAL NOT NULL,
                max_drawdown REAL NOT NULL,
                volume_ratio REAL NOT NULL,
                sto_bull_ratio REAL NOT NULL,
                ma_bull_ratio REAL NOT NULL,
                weekly_high_ratio REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_replay_vectors_symbol ON replay_event_vectors(market, ticker, event_date)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_replay_vectors_version ON replay_event_vectors(ade_version, vector_version)"
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def build(self, ade_version: str | None = None, rebuild: bool = False) -> ReplayVectorBuildStats:
        if rebuild:
            if ade_version is None:
                self.conn.execute("DELETE FROM replay_event_vectors")
            else:
                self.conn.execute("DELETE FROM replay_event_vectors WHERE ade_version=?", (ade_version,))
            self.conn.commit()

        where = ""
        params: list[object] = []
        if ade_version is not None:
            where = "WHERE e.ade_version=?"
            params.append(ade_version)

        events = self.conn.execute(
            f"""
            SELECT e.event_id, e.ade_version, e.market, e.ticker, e.event_date
            FROM replay_events e
            {where}
            ORDER BY e.event_date, e.event_id
            """,
            params,
        ).fetchall()

        upserted = 0
        skipped = 0
        for event in events:
            flows = self.conn.execute(
                """
                SELECT day_index, close, volume, return_pct, drawdown_pct,
                       sto_state, ma_state, weekly_position
                FROM replay_event_flow
                WHERE event_id=?
                ORDER BY day_index
                """,
                (event["event_id"],),
            ).fetchall()
            vector = self._extract(flows)
            if vector is None:
                skipped += 1
                continue
            self._upsert(event, vector)
            upserted += 1
            if upserted % 1000 == 0:
                self.conn.commit()

        self.conn.commit()
        total = int(self.conn.execute("SELECT COUNT(*) FROM replay_event_vectors").fetchone()[0])
        return ReplayVectorBuildStats(
            scanned_events=len(events),
            upserted_vectors=upserted,
            skipped_events=skipped,
            total_vectors=total,
        )

    @staticmethod
    def _extract(flows: list[sqlite3.Row]) -> dict[str, object] | None:
        if len(flows) < 5:
            return None

        returns = np.array([float(row["return_pct"] or 0.0) for row in flows], dtype=float)
        drawdowns = np.array([float(row["drawdown_pct"] or 0.0) for row in flows], dtype=float)
        volumes = np.array([float(row["volume"] or 0.0) for row in flows], dtype=float)

        daily_changes = np.diff(returns, prepend=returns[0])
        volatility = float(np.std(daily_changes)) if len(daily_changes) else 0.0
        base_volume = float(np.mean(volumes[: min(5, len(volumes))])) if len(volumes) else 0.0
        recent_volume = float(np.mean(volumes[-min(5, len(volumes)) :])) if len(volumes) else 0.0
        volume_ratio = recent_volume / base_volume if base_volume > 0 else 1.0

        sto_bull_ratio = ReplayEventVectorBuilder._state_ratio(
            [str(row["sto_state"] or "") for row in flows],
            ("BULL", "UP", "GOLDEN", "RISING", "정배열", "상승"),
        )
        ma_bull_ratio = ReplayEventVectorBuilder._state_ratio(
            [str(row["ma_state"] or "") for row in flows],
            ("BULL", "UP", "GOLDEN", "RISING", "정배열", "상승"),
        )
        weekly_high_ratio = ReplayEventVectorBuilder._state_ratio(
            [str(row["weekly_position"] or "") for row in flows],
            ("HIGH", "ABOVE", "UPPER", "상단", "위"),
        )

        return_5d = float(returns[min(4, len(returns) - 1)])
        return_20d = float(returns[min(19, len(returns) - 1)])
        return_last = float(returns[-1])
        max_drawdown = float(np.min(drawdowns)) if len(drawdowns) else 0.0

        raw = [
            return_5d,
            return_20d,
            return_last,
            volatility,
            max_drawdown,
            math.log1p(max(volume_ratio, 0.0)),
            sto_bull_ratio * 100.0,
            ma_bull_ratio * 100.0,
            weekly_high_ratio * 100.0,
            min(len(flows), 260) / 260.0 * 100.0,
        ]
        vector = ReplayEventVectorBuilder._normalize(raw)
        return {
            "vector": vector,
            "flow_days": len(flows),
            "return_5d": return_5d,
            "return_20d": return_20d,
            "return_last": return_last,
            "volatility": volatility,
            "max_drawdown": max_drawdown,
            "volume_ratio": volume_ratio,
            "sto_bull_ratio": sto_bull_ratio,
            "ma_bull_ratio": ma_bull_ratio,
            "weekly_high_ratio": weekly_high_ratio,
        }

    @staticmethod
    def _state_ratio(values: list[str], positive_tokens: tuple[str, ...]) -> float:
        if not values:
            return 0.0
        positives = 0
        for value in values:
            upper = value.upper()
            if any(token.upper() in upper for token in positive_tokens):
                positives += 1
        return positives / len(values)

    @staticmethod
    def _normalize(values: list[float]) -> list[float]:
        arr = np.asarray(values, dtype=float)
        norm = float(np.linalg.norm(arr))
        if norm <= 0:
            return [0.0 for _ in values]
        return [round(float(value), 8) for value in arr / norm]

    def _upsert(self, event: sqlite3.Row, values: dict[str, object]) -> None:
        self.conn.execute(
            """
            INSERT INTO replay_event_vectors (
                event_id, ade_version, market, ticker, event_date,
                vector_version, vector_json, flow_days,
                return_5d, return_20d, return_last, volatility,
                max_drawdown, volume_ratio, sto_bull_ratio,
                ma_bull_ratio, weekly_high_ratio, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(event_id) DO UPDATE SET
                ade_version=excluded.ade_version,
                market=excluded.market,
                ticker=excluded.ticker,
                event_date=excluded.event_date,
                vector_version=excluded.vector_version,
                vector_json=excluded.vector_json,
                flow_days=excluded.flow_days,
                return_5d=excluded.return_5d,
                return_20d=excluded.return_20d,
                return_last=excluded.return_last,
                volatility=excluded.volatility,
                max_drawdown=excluded.max_drawdown,
                volume_ratio=excluded.volume_ratio,
                sto_bull_ratio=excluded.sto_bull_ratio,
                ma_bull_ratio=excluded.ma_bull_ratio,
                weekly_high_ratio=excluded.weekly_high_ratio,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                event["event_id"], event["ade_version"], event["market"],
                event["ticker"], event["event_date"], VECTOR_VERSION,
                json.dumps(values["vector"], separators=(",", ":")),
                values["flow_days"], values["return_5d"], values["return_20d"],
                values["return_last"], values["volatility"], values["max_drawdown"],
                values["volume_ratio"], values["sto_bull_ratio"],
                values["ma_bull_ratio"], values["weekly_high_ratio"],
            ),
        )
