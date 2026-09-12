"""Read-only projections for the decision desk. Never calculates recommendation scores."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


from recommendation.evidence import (
    Evidence,
    decode as decode,
    number as number,
    table_exists,
    read_live_evidence,
    read_saved_evidence,
)
from recommendation.run_context import (
    completed_run_by_id,
    completed_runs,
    load_run_context,
)


class DeskData:
    def __init__(self, path: str | Path, market: str) -> None:
        self.path = Path(path)
        self.market = market

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(
            self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        try:
            yield conn
        finally:
            conn.close()

    def runs(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.connect() as conn:
            return completed_runs(conn, self.market)

    def context(self, run_id: str):
        with self.connect() as conn:
            return load_run_context(conn, self.market, run_id)

    def run(self, run_id: str):
        with self.connect() as conn:
            return completed_run_by_id(conn, self.market, run_id)

    def health(self) -> dict:
        if not self.path.exists():
            return {
                "available": False,
                "prices": None,
                "patterns": None,
                "latest_date": None,
            }
        with self.connect() as conn:
            prices = latest_date = patterns = None
            if table_exists(conn, "price_bars"):
                row = conn.execute(
                    "SELECT COUNT(DISTINCT ticker),MAX(trade_date) FROM price_bars WHERE market=?",
                    (self.market,),
                ).fetchone()
                prices, latest_date = row
            if table_exists(conn, "surge_patterns"):
                patterns = conn.execute(
                    "SELECT COUNT(*) FROM surge_patterns WHERE market=?", (self.market,)
                ).fetchone()[0]
            return {
                "available": True,
                "prices": prices,
                "patterns": patterns,
                "latest_date": latest_date,
            }

    def ledger(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.connect() as conn:
            if not table_exists(conn, "ade_runs"):
                return []
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT run_id,kind,ticker,status,created_at,finished_at,error FROM ade_runs "
                    "WHERE market=? ORDER BY created_at DESC LIMIT 50",
                    (self.market,),
                )
            ]

    def stages(self, run_id: str) -> list[dict]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT name,status,started_at,finished_at,error FROM ade_run_stages WHERE run_id=? ORDER BY ordinal",
                    (run_id,),
                )
            ]

    def evidence(self, selected: dict, match: dict, cutoff: str) -> Evidence:
        with self.connect() as conn:
            # Keep a consistent read snapshot across metadata and price queries.
            conn.execute("BEGIN")
            saved = read_saved_evidence(conn, self.market, selected, match)
            return (
                saved
                if saved is not None
                else read_live_evidence(conn, self.market, selected, match, cutoff)
            )
