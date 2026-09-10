"""Read-only projections for the decision desk. Never calculates recommendation scores."""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from recommendation.run_context import (
    completed_run_by_id,
    completed_runs,
    load_run_context,
)


def decode(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value or "{}")
    except (ValueError, TypeError):
        return {}
    return result if isinstance(result, dict) else {}


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


@dataclass(frozen=True)
class Evidence:
    current: pd.DataFrame
    historical: pd.DataFrame
    pattern: dict
    warnings: tuple[str, ...]
    source: str


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

    @staticmethod
    def _frame(rows) -> pd.DataFrame:
        frame = pd.DataFrame([dict(row) for row in rows])
        return frame.rename(
            columns={
                "trade_date": "Date",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            }
        )

    def evidence(self, selected: dict, match: dict, cutoff: str) -> Evidence:
        warnings = []
        payload = decode(selected.get("payload_json"))
        source_date = str(payload.get("recent_event_date") or cutoff)[:10]
        ticker = str(selected["ticker"])
        source = ""
        current = historical = pd.DataFrame()
        pattern = {}
        with self.connect() as conn:
            if table_exists(conn, "price_bars"):
                source_row = conn.execute(
                    "SELECT source,COUNT(*) AS n FROM price_bars WHERE market=? AND ticker=? AND trade_date<=? "
                    "GROUP BY source ORDER BY (source=?) DESC,n DESC,source LIMIT 1",
                    (
                        self.market,
                        ticker,
                        source_date,
                        "fdr" if self.market == "kr" else "yfinance",
                    ),
                ).fetchone()
                if source_row:
                    source = str(source_row["source"])
                    current = (
                        self._frame(
                            conn.execute(
                                "SELECT * FROM price_bars WHERE market=? AND ticker=? AND source=? AND trade_date<=? "
                                "ORDER BY trade_date DESC LIMIT 120",
                                (self.market, ticker, source, source_date),
                            ).fetchall()
                        )
                        .sort_values("Date")
                        .reset_index(drop=True)
                    )
            if match and table_exists(conn, "surge_patterns"):
                pattern_id = str(match.get("pattern_id") or "")
                event_id = str(
                    match.get("source_event_id") or match.get("event_id") or ""
                )
                event_date = str(match.get("event_date") or "")[:10]
                # The source event can have several surges; never pick a different surge by recency.
                rows = conn.execute(
                    "SELECT * FROM surge_patterns WHERE market=? AND "
                    "(pattern_id=? OR (source_event_id=? AND surge_start_date=?))",
                    (
                        str(match.get("market") or self.market),
                        pattern_id or event_id,
                        event_id,
                        event_date,
                    ),
                ).fetchall()
                if len(rows) == 1:
                    pattern = dict(rows[0])
                    if table_exists(conn, "surge_pattern_bars"):
                        historical = self._frame(
                            conn.execute(
                                "SELECT * FROM surge_pattern_bars WHERE pattern_id=? ORDER BY day_index",
                                (pattern["pattern_id"],),
                            ).fetchall()
                        )
                elif len(rows) > 1:
                    warnings.append(
                        "동일 사례의 패턴 버전이 여러 개입니다. 원천 패턴을 확정할 수 없습니다."
                    )
        if len(current) < 120:
            warnings.append(
                f"추천 시점 가격 이력이 {len(current)}거래일입니다. 120거래일 비교 자료가 필요합니다."
            )
        if len(historical) < 120:
            warnings.append(
                "선택한 과거 사례의 120거래일 원천 차트가 충분하지 않습니다."
            )
        return Evidence(current, historical, pattern, tuple(warnings), source)
