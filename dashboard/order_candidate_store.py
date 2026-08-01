from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


_DB_PATH = Path(os.getenv("ADE_UI_STATE_DB", "output/ade_ui_state.sqlite3"))
_LEGACY_JSON_PATH = Path("output/ade_order_candidates.json")
_LEGACY_OWNER_ID = "legacy-import"
_LOCK = threading.RLock()
_SCHEMA_READY = False
_MAX_CANDIDATES_PER_OWNER = 100


class OrderCandidateStoreError(RuntimeError):
    pass


def _connect() -> sqlite3.Connection:
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn
    except Exception as exc:  # pragma: no cover - surfaced to UI
        raise OrderCandidateStoreError(f"주문후보 DB 연결 실패: {exc}") from exc


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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_order_candidates_owner_added ON order_candidates(owner_id, added_at DESC)"
            )
        _SCHEMA_READY = True


def _migrate_legacy_once() -> None:
    _ensure_schema()
    with _LOCK, _connect() as conn:
        done = conn.execute("SELECT value FROM app_meta WHERE key='legacy_candidates_migrated'").fetchone()
        if done:
            return
        rows: list[dict[str, Any]] = []
        if _LEGACY_JSON_PATH.exists():
            try:
                payload = json.loads(_LEGACY_JSON_PATH.read_text(encoding="utf-8"))
                rows = payload if isinstance(payload, list) else []
            except Exception as exc:
                raise OrderCandidateStoreError(f"기존 주문후보 JSON 읽기 실패: {exc}") from exc
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
                (_LEGACY_OWNER_ID, market, ticker, symbol, added_at),
            )
        conn.execute(
            "INSERT OR REPLACE INTO app_meta(key, value) VALUES('legacy_candidates_migrated', ?)",
            (datetime.now().isoformat(timespec="seconds"),),
        )


def upsert_candidate(owner_id: str, market: str, ticker: str, symbol: str) -> None:
    _migrate_legacy_once()
    added_at = datetime.now().isoformat(timespec="microseconds")
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
        conn.execute(
            """
            DELETE FROM order_candidates
            WHERE owner_id=? AND rowid NOT IN (
                SELECT rowid FROM order_candidates
                WHERE owner_id=?
                ORDER BY COALESCE(last_selected_at, added_at) DESC, added_at DESC
                LIMIT ?
            )
            """,
            (owner_id, owner_id, _MAX_CANDIDATES_PER_OWNER),
        )


def list_candidates(owner_id: str, market: str | None = None) -> list[dict[str, Any]]:
    _migrate_legacy_once()
    sql = "SELECT market, ticker, symbol, added_at, last_selected_at FROM order_candidates WHERE owner_id=?"
    params: list[Any] = [owner_id]
    if market:
        sql += " AND market=?"
        params.append(market)
    sql += " ORDER BY COALESCE(last_selected_at, added_at) DESC, added_at DESC"
    with _LOCK, _connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def list_legacy_candidates(market: str | None = None) -> list[dict[str, Any]]:
    return list_candidates(_LEGACY_OWNER_ID, market)


def mark_selected(owner_id: str, market: str, ticker: str) -> None:
    _migrate_legacy_once()
    selected_at = datetime.now().isoformat(timespec="microseconds")
    with _LOCK, _connect() as conn:
        conn.execute(
            "UPDATE order_candidates SET last_selected_at=? WHERE owner_id=? AND market=? AND ticker=?",
            (selected_at, owner_id, market, ticker),
        )


def delete_candidate(owner_id: str, market: str, ticker: str) -> None:
    _migrate_legacy_once()
    with _LOCK, _connect() as conn:
        conn.execute(
            "DELETE FROM order_candidates WHERE owner_id=? AND market=? AND ticker=?",
            (owner_id, market, ticker),
        )


def clear_candidates(owner_id: str, market: str | None = None) -> None:
    _migrate_legacy_once()
    with _LOCK, _connect() as conn:
        if market:
            conn.execute("DELETE FROM order_candidates WHERE owner_id=? AND market=?", (owner_id, market))
        else:
            conn.execute("DELETE FROM order_candidates WHERE owner_id=?", (owner_id,))


def store_health() -> dict[str, Any]:
    try:
        _ensure_schema()
        with _connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "정상", "path": str(_DB_PATH), "writable": os.access(_DB_PATH.parent, os.W_OK)}
    except Exception as exc:
        return {"status": "오류", "path": str(_DB_PATH), "error": str(exc), "writable": False}
