from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from broker.kis import kis_broker_from_env


@dataclass(frozen=True)
class KISAccountSnapshot:
    captured_at: str
    cash: float
    position_count: int
    evaluation_amount: float
    pnl: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class KISAccountSync:
    """Synchronize KIS paper-account balances into the ADE SQLite database."""

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kis_account_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                cash REAL NOT NULL,
                position_count INTEGER NOT NULL,
                evaluation_amount REAL NOT NULL,
                pnl REAL NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kis_position_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                quantity INTEGER NOT NULL,
                average_price REAL NOT NULL,
                current_price REAL NOT NULL,
                evaluation_amount REAL NOT NULL,
                pnl REAL NOT NULL,
                pnl_rate REAL NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kis_account_time ON kis_account_snapshots(captured_at)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kis_position_time ON kis_position_snapshots(captured_at, ticker)")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def sync(self) -> tuple[KISAccountSnapshot, list[dict[str, object]]]:
        broker = kis_broker_from_env()
        cash = float(broker.get_cash())
        positions = broker.get_positions()
        captured_at = datetime.now().isoformat(timespec="seconds")
        evaluation_amount = sum(float(item.evaluation_amount) for item in positions)
        pnl = sum(float(item.pnl) for item in positions)

        snapshot = KISAccountSnapshot(
            captured_at=captured_at,
            cash=cash,
            position_count=len(positions),
            evaluation_amount=evaluation_amount,
            pnl=pnl,
        )
        self.conn.execute(
            """
            INSERT INTO kis_account_snapshots(captured_at, cash, position_count, evaluation_amount, pnl)
            VALUES (?, ?, ?, ?, ?)
            """,
            (captured_at, cash, len(positions), evaluation_amount, pnl),
        )
        rows: list[dict[str, object]] = []
        for item in positions:
            row = {
                "captured_at": captured_at,
                "market": item.market,
                "ticker": item.ticker,
                "name": item.name,
                "quantity": item.quantity,
                "average_price": item.average_price,
                "current_price": item.current_price,
                "evaluation_amount": item.evaluation_amount,
                "pnl": item.pnl,
                "pnl_rate": item.pnl_rate,
            }
            rows.append(row)
            self.conn.execute(
                """
                INSERT INTO kis_position_snapshots(
                    captured_at, market, ticker, name, quantity, average_price,
                    current_price, evaluation_amount, pnl, pnl_rate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    captured_at, item.market, item.ticker, item.name, item.quantity,
                    item.average_price, item.current_price, item.evaluation_amount,
                    item.pnl, item.pnl_rate,
                ),
            )
        self.conn.commit()
        return snapshot, rows

    def latest_account(self) -> dict[str, object] | None:
        row = self.conn.execute(
            "SELECT * FROM kis_account_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row is not None else None

    def latest_positions(self) -> list[dict[str, object]]:
        latest = self.conn.execute(
            "SELECT captured_at FROM kis_account_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if latest is None:
            return []
        rows = self.conn.execute(
            """
            SELECT market, ticker, name, quantity, average_price, current_price,
                   evaluation_amount, pnl, pnl_rate, captured_at
            FROM kis_position_snapshots
            WHERE captured_at=?
            ORDER BY evaluation_amount DESC
            """,
            (latest["captured_at"],),
        ).fetchall()
        return [dict(row) for row in rows]

    def account_history(self, limit: int = 200) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """
            SELECT captured_at, cash, position_count, evaluation_amount, pnl
            FROM kis_account_snapshots
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]
