from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from pattern.vector import PatternVector, PatternVectorizer


MEMORY_VERSION = "pattern-memory-v1.0.0"


@dataclass(frozen=True)
class PatternMemoryRecord:
    market: str
    ticker: str
    trade_date: str
    vector_version: str
    window: int
    vector: list[float]
    close: float
    forward_returns: dict[str, float]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatternMemoryMatch:
    market: str
    ticker: str
    trade_date: str
    similarity: float
    close: float
    forward_returns: dict[str, float]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PatternMemoryRepository:
    """SQLite-backed pattern memory for deterministic local vector search.

    v1.0 stores pattern vectors as JSON and performs brute-force cosine search.
    This keeps the interface stable before migrating to FAISS/Qdrant in v2.0.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pattern_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                memory_version TEXT NOT NULL,
                vector_version TEXT NOT NULL,
                window INTEGER NOT NULL,
                vector_json TEXT NOT NULL,
                close REAL NOT NULL,
                forward_returns_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (market, ticker, trade_date, memory_version, vector_version, window)
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pattern_memory_lookup
            ON pattern_memory (market, ticker, trade_date, memory_version, vector_version, window)
            """
        )
        self.conn.commit()

    def upsert(self, record: PatternMemoryRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO pattern_memory (
                market, ticker, trade_date, memory_version, vector_version, window,
                vector_json, close, forward_returns_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market, ticker, trade_date, memory_version, vector_version, window)
            DO UPDATE SET
                vector_json=excluded.vector_json,
                close=excluded.close,
                forward_returns_json=excluded.forward_returns_json,
                metadata_json=excluded.metadata_json
            """,
            (
                record.market,
                record.ticker,
                record.trade_date,
                MEMORY_VERSION,
                record.vector_version,
                record.window,
                json.dumps(record.vector),
                record.close,
                json.dumps(record.forward_returns),
                json.dumps(record.metadata),
            ),
        )
        self.conn.commit()

    def bulk_upsert(self, records: Iterable[PatternMemoryRecord]) -> int:
        count = 0
        for record in records:
            self.upsert(record)
            count += 1
        return count

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS cnt FROM pattern_memory").fetchone()
        return int(row["cnt"])

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        market: str | None = None,
        ticker: str | None = None,
        exclude_trade_date: str | None = None,
    ) -> list[PatternMemoryMatch]:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        params: list[Any] = []
        where = ["1=1"]
        if market:
            where.append("market = ?")
            params.append(market)
        if ticker:
            where.append("ticker = ?")
            params.append(ticker)
        if exclude_trade_date:
            where.append("trade_date <> ?")
            params.append(exclude_trade_date)

        rows = self.conn.execute(
            f"SELECT * FROM pattern_memory WHERE {' AND '.join(where)}",
            params,
        ).fetchall()
        query = np.asarray(query_vector, dtype=float)
        matches: list[PatternMemoryMatch] = []
        for row in rows:
            vector = np.asarray(json.loads(row["vector_json"]), dtype=float)
            similarity = self._cosine_similarity(query, vector)
            matches.append(
                PatternMemoryMatch(
                    market=row["market"],
                    ticker=row["ticker"],
                    trade_date=row["trade_date"],
                    similarity=round(similarity, 6),
                    close=float(row["close"]),
                    forward_returns=json.loads(row["forward_returns_json"]),
                    metadata=json.loads(row["metadata_json"]),
                )
            )
        return sorted(matches, key=lambda item: item.similarity, reverse=True)[:top_k]

    def close(self) -> None:
        self.conn.close()

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)


class PatternMemoryBuilder:
    """Build pattern memory records from OHLCV history."""

    def __init__(self, window: int = 20, horizons: tuple[int, ...] = (5, 10, 20, 40)) -> None:
        self.window = window
        self.horizons = horizons
        self.vectorizer = PatternVectorizer(window=window)

    def build_records(self, df: pd.DataFrame, market: str, ticker: str) -> list[PatternMemoryRecord]:
        self._validate(df)
        records: list[PatternMemoryRecord] = []
        max_horizon = max(self.horizons)
        last_index = len(df) - 1 - max_horizon
        for end_index in range(self.window - 1, last_index + 1):
            vector = self.vectorizer.transform_window(df, end_index=end_index, ticker=ticker)
            trade_date = self._trade_date(df, end_index)
            close = float(df.iloc[end_index]["Close"])
            records.append(
                PatternMemoryRecord(
                    market=market,
                    ticker=ticker,
                    trade_date=trade_date,
                    vector_version=vector.vector_version,
                    window=vector.window,
                    vector=vector.values,
                    close=close,
                    forward_returns=self._forward_returns(df, end_index),
                    metadata={"end_index": end_index, **vector.metadata},
                )
            )
        return records

    def _validate(self, df: pd.DataFrame) -> None:
        required = {"Open", "High", "Low", "Close", "Volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Pattern memory requires columns: {', '.join(sorted(missing))}")
        min_len = self.window + max(self.horizons) + 1
        if len(df) < min_len:
            raise ValueError(f"Pattern memory requires at least {min_len} rows")

    def _trade_date(self, df: pd.DataFrame, end_index: int) -> str:
        if "Date" in df.columns:
            return str(df.iloc[end_index]["Date"])
        idx = df.index[end_index]
        return str(idx.date()) if hasattr(idx, "date") else str(end_index)

    def _forward_returns(self, df: pd.DataFrame, end_index: int) -> dict[str, float]:
        base = float(df.iloc[end_index]["Close"])
        returns: dict[str, float] = {}
        for horizon in self.horizons:
            future_close = float(df.iloc[end_index + horizon]["Close"])
            returns[f"return_{horizon}d"] = (future_close - base) / base if base > 0 else 0.0
        return returns


def build_pattern_memory(
    df: pd.DataFrame,
    market: str,
    ticker: str,
    repository: PatternMemoryRepository,
    window: int = 20,
    horizons: tuple[int, ...] = (5, 10, 20, 40),
) -> int:
    records = PatternMemoryBuilder(window=window, horizons=horizons).build_records(df, market=market, ticker=ticker)
    return repository.bulk_upsert(records)
