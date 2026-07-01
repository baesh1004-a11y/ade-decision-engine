from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backtest.metrics import MetricsEngine
from backtest.models import BacktestResult


class BacktestRepository:
    """SQLite persistence for ADE backtest results."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                initial_cash REAL NOT NULL,
                final_equity REAL NOT NULL,
                total_return REAL NOT NULL,
                max_drawdown REAL NOT NULL,
                trade_count INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                reasons_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                exit_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                shares INTEGER NOT NULL,
                gross_return REAL NOT NULL,
                holding_days INTEGER NOT NULL,
                reason TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES backtest_runs_v2(id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_daily_equity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                trade_date TEXT NOT NULL,
                cash REAL NOT NULL,
                position_value REAL NOT NULL,
                equity REAL NOT NULL,
                drawdown REAL NOT NULL,
                FOREIGN KEY (run_id) REFERENCES backtest_runs_v2(id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_performance_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                trade_count INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                avg_return REAL NOT NULL,
                avg_win REAL NOT NULL,
                avg_loss REAL NOT NULL,
                profit_factor REAL NOT NULL,
                expectancy REAL NOT NULL,
                total_return REAL NOT NULL,
                max_drawdown REAL NOT NULL,
                FOREIGN KEY (run_id) REFERENCES backtest_runs_v2(id)
            )
            """
        )
        self.conn.commit()

    def save_result(self, result: BacktestResult | dict[str, Any]) -> int:
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        cursor = self.conn.execute(
            """
            INSERT INTO backtest_runs_v2 (
                ticker, start_date, end_date, initial_cash, final_equity,
                total_return, max_drawdown, trade_count, win_rate, reasons_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["ticker"],
                payload["start_date"],
                payload["end_date"],
                float(payload["initial_cash"]),
                float(payload["final_equity"]),
                float(payload["total_return"]),
                float(payload["max_drawdown"]),
                int(payload["trade_count"]),
                float(payload["win_rate"]),
                json.dumps(payload.get("reasons", [])),
            ),
        )
        run_id = int(cursor.lastrowid)
        self._save_trades(run_id, payload.get("trades", []))
        self._save_daily_equity(run_id, payload.get("daily_equity", []))
        self._save_summary(run_id, payload)
        self.conn.commit()
        return run_id

    def fetch_run(self, run_id: int) -> dict[str, Any]:
        run = self.conn.execute("SELECT * FROM backtest_runs_v2 WHERE id = ?", (run_id,)).fetchone()
        if run is None:
            raise ValueError("backtest run not found")
        trades = self.conn.execute("SELECT * FROM backtest_trades WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        daily = self.conn.execute("SELECT * FROM backtest_daily_equity WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        summary = self.conn.execute("SELECT * FROM backtest_performance_summary WHERE run_id = ?", (run_id,)).fetchone()
        return {
            "run": dict(run),
            "trades": [dict(row) for row in trades],
            "daily_equity": [dict(row) for row in daily],
            "summary": dict(summary) if summary else None,
        }

    def count_runs(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS cnt FROM backtest_runs_v2").fetchone()
        return int(row["cnt"])

    def close(self) -> None:
        self.conn.close()

    def _save_trades(self, run_id: int, trades: list[dict[str, Any]]) -> None:
        for trade in trades:
            self.conn.execute(
                """
                INSERT INTO backtest_trades (
                    run_id, ticker, entry_date, exit_date, entry_price, exit_price,
                    shares, gross_return, holding_days, reason, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    trade["ticker"],
                    trade["entry_date"],
                    trade["exit_date"],
                    float(trade["entry_price"]),
                    float(trade["exit_price"]),
                    int(trade["shares"]),
                    float(trade["gross_return"]),
                    int(trade["holding_days"]),
                    str(trade["reason"]),
                    json.dumps(trade.get("metadata", {})),
                ),
            )

    def _save_daily_equity(self, run_id: int, daily_equity: list[dict[str, Any]]) -> None:
        for item in daily_equity:
            self.conn.execute(
                """
                INSERT INTO backtest_daily_equity (
                    run_id, trade_date, cash, position_value, equity, drawdown
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    item["trade_date"],
                    float(item["cash"]),
                    float(item["position_value"]),
                    float(item["equity"]),
                    float(item["drawdown"]),
                ),
            )

    def _save_summary(self, run_id: int, payload: dict[str, Any]) -> None:
        summary = MetricsEngine().summarize(payload).to_dict()
        self.conn.execute(
            """
            INSERT INTO backtest_performance_summary (
                run_id, trade_count, win_rate, avg_return, avg_win, avg_loss,
                profit_factor, expectancy, total_return, max_drawdown
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                int(summary["trade_count"]),
                float(summary["win_rate"]),
                float(summary["avg_return"]),
                float(summary["avg_win"]),
                float(summary["avg_loss"]),
                float(summary["profit_factor"]),
                float(summary["expectancy"]),
                float(summary["total_return"]),
                float(summary["max_drawdown"]),
            ),
        )
