from __future__ import annotations

import sqlite3
from pathlib import Path

from replay.models import ReplayEvent, ReplayEventFlow


class ReplayEventRepository:
    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS replay_events (
                event_id TEXT PRIMARY KEY,
                ade_version TEXT NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                event_date TEXT NOT NULL,
                money_ratio_20d REAL NOT NULL,
                money_ratio_120d REAL NOT NULL,
                bullish_body INTEGER NOT NULL,
                long_base INTEGER NOT NULL,
                sto_state TEXT NOT NULL,
                ma_state TEXT NOT NULL,
                weekly_position TEXT NOT NULL,
                money_flow TEXT NOT NULL,
                year_center REAL,
                half_center REAL,
                quarter_center REAL,
                month_center REAL,
                event_end_date TEXT,
                event_end_reason TEXT,
                max_return REAL,
                max_drawdown REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS replay_event_flow (
                event_id TEXT NOT NULL,
                day_index INTEGER NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                return_pct REAL NOT NULL,
                drawdown_pct REAL NOT NULL,
                sto_state TEXT NOT NULL,
                ma_state TEXT NOT NULL,
                weekly_position TEXT NOT NULL,
                PRIMARY KEY(event_id, day_index)
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_events_state ON replay_events (sto_state, ma_state, weekly_position, money_flow)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_events_symbol ON replay_events (market, ticker, event_date)")
        self.conn.commit()

    def clear(self, ade_version: str | None = None) -> None:
        if ade_version is None:
            self.conn.execute("DELETE FROM replay_event_flow")
            self.conn.execute("DELETE FROM replay_events")
        else:
            ids = [row["event_id"] for row in self.conn.execute("SELECT event_id FROM replay_events WHERE ade_version=?", (ade_version,)).fetchall()]
            for event_id in ids:
                self.conn.execute("DELETE FROM replay_event_flow WHERE event_id=?", (event_id,))
            self.conn.execute("DELETE FROM replay_events WHERE ade_version=?", (ade_version,))
        self.conn.commit()

    def upsert_event(self, event: ReplayEvent) -> None:
        self.conn.execute(
            """
            INSERT INTO replay_events (
                event_id, ade_version, market, ticker, name, event_date,
                money_ratio_20d, money_ratio_120d, bullish_body, long_base,
                sto_state, ma_state, weekly_position, money_flow,
                year_center, half_center, quarter_center, month_center,
                event_end_date, event_end_reason, max_return, max_drawdown
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                money_ratio_20d=excluded.money_ratio_20d,
                money_ratio_120d=excluded.money_ratio_120d,
                bullish_body=excluded.bullish_body,
                long_base=excluded.long_base,
                sto_state=excluded.sto_state,
                ma_state=excluded.ma_state,
                weekly_position=excluded.weekly_position,
                money_flow=excluded.money_flow,
                year_center=excluded.year_center,
                half_center=excluded.half_center,
                quarter_center=excluded.quarter_center,
                month_center=excluded.month_center,
                event_end_date=excluded.event_end_date,
                event_end_reason=excluded.event_end_reason,
                max_return=excluded.max_return,
                max_drawdown=excluded.max_drawdown
            """,
            (
                event.event_id, event.ade_version, event.market, event.ticker, event.name, event.event_date,
                event.money_ratio_20d, event.money_ratio_120d, int(event.bullish_body), int(event.long_base),
                event.sto_state, event.ma_state, event.weekly_position, event.money_flow,
                event.year_center, event.half_center, event.quarter_center, event.month_center,
                event.event_end_date, event.event_end_reason, event.max_return, event.max_drawdown,
            ),
        )

    def replace_flow(self, event_id: str, flows: list[ReplayEventFlow]) -> None:
        self.conn.execute("DELETE FROM replay_event_flow WHERE event_id=?", (event_id,))
        self.conn.executemany(
            """
            INSERT INTO replay_event_flow (
                event_id, day_index, trade_date, close, volume, return_pct,
                drawdown_pct, sto_state, ma_state, weekly_position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f.event_id, f.day_index, f.trade_date, f.close, f.volume, f.return_pct,
                    f.drawdown_pct, f.sto_state, f.ma_state, f.weekly_position,
                )
                for f in flows
            ],
        )

    def commit(self) -> None:
        self.conn.commit()

    def counts(self) -> tuple[int, int]:
        events = self.conn.execute("SELECT COUNT(*) AS c FROM replay_events").fetchone()["c"]
        flows = self.conn.execute("SELECT COUNT(*) AS c FROM replay_event_flow").fetchone()["c"]
        return int(events), int(flows)

    def close(self) -> None:
        self.conn.close()
