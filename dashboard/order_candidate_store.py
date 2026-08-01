from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


_DB_PATH = Path("output/ade_ui_state.sqlite3")
_LEGACY_JSON_PATH = Path("output/ade_order_candidates.json")
_LOCK = threading.RLock()
_SCHEMA_READY = False
_LEGACY_MIGRATED = False


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_schema() -> None:
    global _SCHEMA_READY
    with _LOCK:
        if _SCHEMA_READY:
            return
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS order_candidates (
                    owner_id TEXT NOT NULL,
                    market TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    last_selected_at TEXT,
                    PRIMARY KEY (owner_id, market, ticker)
                )
                """
            )
        _SCHEMA_READY = True


def _migrate_legacy(owner_id: str) -> None:
    global _LEGACY_MIGRATED
    with _LOCK:
        if _LEGACY_MIGRATED or not _LEGACY_JSON_PATH.exists():
            _LEGACY_MIGRATED = True
            return
        try:
            payload = json.loads(_LEGACY_JSON_PATH.read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else []
        except Exception:
            rows = []
        if rows:
            with _connect() as conn:
                for row in rows:
                    market = str(row.get("market") or "").strip()
                    ticker = str(row.get("ticker") or "").strip()
                    symbol = str(row.get("symbol") or ticker).strip()
                    if not market or not ticker:
                        continue
                    added_at = str(row.get("added_at") or datetime.now().isoformat(timespec="seconds"))
                    conn.execute(
                        """
                        INSERT INTO order_candidates(owner_id, market, ticker, symbol, added_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(owner_id, market, ticker) DO UPDATE SET
                            symbol=excluded.symbol,
                            added_at=excluded.added_at
                        """,
                        (owner_id, market, ticker, symbol, added_at),
                    )
        _LEGACY_MIGRATED = True


def upsert_candidate(owner_id: str, market: str, ticker: str, symbol: str) -> None:
    _ensure_schema()
    _migrate_legacy(owner_id)
    added_at = datetime.now().isoformat(timespec="seconds")
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO order_candidates(owner_id, market, ticker, symbol, added_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(owner_id, market, ticker) DO UPDATE SET
                symbol=excluded.symbol,
                added_at=excluded.added_at
            """,
            (owner_id, market, ticker, symbol, added_at),
        )


def list_candidates(owner_id: str, market: str | None = None) -> list[dict[str, Any]]:
    _ensure_schema()
    _migrate_legacy(owner_id)
    sql = "SELECT market, ticker, symbol, added_at, last_selected_at FROM order_candidates WHERE owner_id=?"
    params: list[Any] = [owner_id]
    if market:
        sql += " AND market=?"
        params.append(market)
    sql += " ORDER BY added_at DESC"
    with _LOCK, _connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def mark_selected(owner_id: str, market: str, ticker: str) -> None:
    _ensure_schema()
    selected_at = datetime.now().isoformat(timespec="seconds")
    with _LOCK, _connect() as conn:
        conn.execute(
            "UPDATE order_candidates SET last_selected_at=? WHERE owner_id=? AND market=? AND ticker=?",
            (selected_at, owner_id, market, ticker),
        )
