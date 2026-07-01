from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd

from datahub.models import PriceBar


class PriceRepository:
    """SQLite repository for normalized OHLCV price data."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                adjusted_close REAL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(market, ticker, trade_date, source)
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_price_bars_lookup
            ON price_bars (market, ticker, trade_date)
            """
        )
        self.conn.commit()

    def upsert_many(self, records: Iterable[PriceBar]) -> int:
        count = 0
        for record in records:
            self.conn.execute(
                """
                INSERT INTO price_bars (
                    market, ticker, trade_date, open, high, low, close, volume, adjusted_close, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(market, ticker, trade_date, source)
                DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    adjusted_close=excluded.adjusted_close
                """,
                (
                    record.market,
                    record.ticker,
                    record.trade_date,
                    record.open,
                    record.high,
                    record.low,
                    record.close,
                    record.volume,
                    record.adjusted_close,
                    record.source,
                ),
            )
            count += 1
        self.conn.commit()
        return count

    def fetch_dataframe(
        self,
        market: str,
        ticker: str,
        start_date: str | None = None,
        end_date: str | None = None,
        source: str | None = None,
    ) -> pd.DataFrame:
        where = ["market = ?", "ticker = ?"]
        params: list[object] = [market, ticker]
        if start_date:
            where.append("trade_date >= ?")
            params.append(start_date)
        if end_date:
            where.append("trade_date <= ?")
            params.append(end_date)
        if source:
            where.append("source = ?")
            params.append(source)
        rows = self.conn.execute(
            f"SELECT trade_date, open, high, low, close, volume, adjusted_close FROM price_bars WHERE {' AND '.join(where)} ORDER BY trade_date",
            params,
        ).fetchall()
        df = pd.DataFrame([dict(row) for row in rows])
        if df.empty:
            return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume", "Adj Close"])
        df = df.rename(
            columns={
                "trade_date": "Date",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
                "adjusted_close": "Adj Close",
            }
        )
        return df

    def count(self, market: str | None = None, ticker: str | None = None) -> int:
        where = ["1=1"]
        params: list[object] = []
        if market:
            where.append("market = ?")
            params.append(market)
        if ticker:
            where.append("ticker = ?")
            params.append(ticker)
        row = self.conn.execute(f"SELECT COUNT(*) AS cnt FROM price_bars WHERE {' AND '.join(where)}", params).fetchone()
        return int(row["cnt"])

    def close(self) -> None:
        self.conn.close()
