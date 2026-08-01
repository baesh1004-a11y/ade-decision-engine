from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from broker.kis import KISBrokerAdapter, kis_broker_from_env


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
    """Persist KIS account snapshots in SQLite with short-lived connections."""

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self, *, readonly: bool = False) -> sqlite3.Connection:
        if readonly and self.db_path.exists():
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=5)
        else:
            conn = sqlite3.connect(str(self.db_path), timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
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
            conn.execute(
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kis_account_time ON kis_account_snapshots(captured_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kis_position_time ON kis_position_snapshots(captured_at, ticker)")

    def close(self) -> None:
        return

    def sync(self, broker: KISBrokerAdapter | None = None) -> tuple[KISAccountSnapshot, list[dict[str, object]]]:
        broker = broker or kis_broker_from_env()
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
        rows: list[dict[str, object]] = []
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kis_account_snapshots(captured_at, cash, position_count, evaluation_amount, pnl)
                VALUES (?, ?, ?, ?, ?)
                """,
                (captured_at, cash, len(positions), evaluation_amount, pnl),
            )
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
                conn.execute(
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
        return snapshot, rows

    def latest_snapshot(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        if not self.db_path.exists():
            return None, []
        with self._connect(readonly=True) as conn:
            account_row = conn.execute(
                "SELECT * FROM kis_account_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if account_row is None:
                return None, []
            positions = conn.execute(
                """
                SELECT market, ticker, name, quantity, average_price, current_price,
                       evaluation_amount, pnl, pnl_rate, captured_at
                FROM kis_position_snapshots
                WHERE captured_at=?
                ORDER BY evaluation_amount DESC
                """,
                (account_row["captured_at"],),
            ).fetchall()
            return dict(account_row), [dict(row) for row in positions]

    def latest_account(self) -> dict[str, object] | None:
        account, _ = self.latest_snapshot()
        return account

    def latest_positions(self) -> list[dict[str, object]]:
        _, positions = self.latest_snapshot()
        return positions

    def account_history(self, limit: int = 200) -> list[dict[str, object]]:
        if not self.db_path.exists():
            return []
        with self._connect(readonly=True) as conn:
            rows = conn.execute(
                """
                SELECT captured_at, cash, position_count, evaluation_amount, pnl
                FROM kis_account_snapshots
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in reversed(rows)]
