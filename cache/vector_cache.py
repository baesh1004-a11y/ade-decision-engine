from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from pattern.replay_probability import ReplayProbabilityEngine
from pattern.shape_similarity import ShapeSimilarityEngine
from universe.manager import DynamicUniverseManager


@dataclass(frozen=True)
class VectorRecord:
    market: str
    ticker: str
    trade_date: str
    vector: list[float]


class VectorCache:
    """SQLite-backed ADE vector cache for fast manual replay analysis."""

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pattern_vectors (
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(market, ticker, trade_date)
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pattern_vectors_lookup
            ON pattern_vectors (market, ticker, trade_date)
            """
        )
        self.conn.commit()

    def upsert(self, record: VectorRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO pattern_vectors (market, ticker, trade_date, vector_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(market, ticker, trade_date)
            DO UPDATE SET vector_json=excluded.vector_json
            """,
            (record.market, record.ticker, record.trade_date, json.dumps(record.vector)),
        )

    def fetch_all(self) -> list[VectorRecord]:
        rows = self.conn.execute("SELECT market, ticker, trade_date, vector_json FROM pattern_vectors").fetchall()
        return [
            VectorRecord(
                market=row["market"],
                ticker=row["ticker"],
                trade_date=row["trade_date"],
                vector=json.loads(row["vector_json"]),
            )
            for row in rows
        ]

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


class VectorBuilder:
    """Build state vectors from OHLCV windows.

    v1 vector is intentionally explainable: current state scores + normalized chart-shape metrics.
    """

    def __init__(self, window: int = 120, step: int = 5) -> None:
        self.window = window
        self.step = step
        self.state_engine = ReplayProbabilityEngine(window=window)
        self.shape_engine = ShapeSimilarityEngine()

    def build_for_dataframe(self, market: str, ticker: str, data: pd.DataFrame) -> list[VectorRecord]:
        prepared = self.state_engine._prepare(data)
        if len(prepared) < self.window:
            return []
        records: list[VectorRecord] = []
        for end in range(self.window, len(prepared) + 1, self.step):
            window_df = prepared.iloc[end - self.window : end].reset_index(drop=True)
            state = self.state_engine.extract_state(window_df)
            shape = self.shape_engine.compare(window_df, window_df)
            vector = [
                state.sto_stack_score / 100,
                state.ma_alignment_score / 100,
                state.weekly_position_score / 100,
                state.volume_surge_score / 100,
                state.long_base_score / 100,
                state.breakout_score / 100,
                state.state_score / 100,
                shape.price_shape_score / 100,
                shape.ma_shape_score / 100,
                shape.volume_shape_score / 100,
                shape.candle_body_score / 100,
                shape.breakout_shape_score / 100,
            ]
            trade_date = str(pd.Timestamp(prepared.iloc[end - 1]["Date"]).date())
            records.append(VectorRecord(market=market, ticker=ticker, trade_date=trade_date, vector=vector))
        return records


def build_vector_cache(db_path: str | Path = "datahub/market.db") -> int:
    repository = PriceRepository(db_path)
    cache = VectorCache(db_path)
    builder = VectorBuilder()
    count = 0
    try:
        for symbol in DynamicUniverseManager().active():
            data = repository.fetch_dataframe(symbol.market, symbol.ticker, source="fdr")
            for record in builder.build_for_dataframe(symbol.market, symbol.ticker, data):
                cache.upsert(record)
                count += 1
        cache.commit()
        return count
    finally:
        repository.close()
        cache.close()
