from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from paper_trading.models import PaperOrderExecution


class PaperPortfolioRepository:
    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def close(self) -> None:
        self.conn.close()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                side TEXT NOT NULL,
                budget INTEGER NOT NULL,
                reference_price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                estimated_amount INTEGER NOT NULL,
                top1_event_id TEXT,
                weekly_similarity REAL,
                sto_similarity REAL,
                final_similarity REAL,
                accepted INTEGER NOT NULL,
                order_id TEXT,
                message TEXT,
                raw TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_paper_orders_lookup
            ON paper_orders (market, ticker, created_at)
            """
        )
        self.conn.commit()

    def save_executions(self, executions: Iterable[PaperOrderExecution]) -> int:
        count = 0
        for execution in executions:
            plan = execution.plan
            self.conn.execute(
                """
                INSERT INTO paper_orders (
                    market, ticker, name, side, budget, reference_price, quantity,
                    estimated_amount, top1_event_id, weekly_similarity, sto_similarity,
                    final_similarity, accepted, order_id, message, raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.market,
                    plan.ticker,
                    plan.name,
                    plan.side,
                    plan.budget,
                    plan.reference_price,
                    plan.quantity,
                    plan.estimated_amount,
                    plan.top1_event_id,
                    plan.weekly_similarity,
                    plan.sto_similarity,
                    plan.final_similarity,
                    1 if execution.accepted else 0,
                    execution.order_id,
                    execution.message,
                    str(execution.raw) if execution.raw is not None else None,
                ),
            )
            count += 1
        self.conn.commit()
        return count

    def open_position_keys(self) -> set[str]:
        """Return market:ticker keys whose accepted net quantity is still positive."""
        rows = self.conn.execute(
            """
            SELECT
                LOWER(market) AS market,
                ticker,
                SUM(
                    CASE
                        WHEN UPPER(side)='BUY' THEN quantity
                        WHEN UPPER(side)='SELL' THEN -quantity
                        ELSE 0
                    END
                ) AS net_quantity
            FROM paper_orders
            WHERE accepted=1
            GROUP BY LOWER(market), ticker
            HAVING net_quantity > 0
            """
        ).fetchall()
        return {f"{str(row['market']).lower()}:{row['ticker']}" for row in rows}

    def is_held(self, market: str, ticker: str) -> bool:
        return f"{market.lower()}:{ticker}" in self.open_position_keys()
