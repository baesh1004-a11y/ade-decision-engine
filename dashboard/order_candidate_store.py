from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DB_PATH = Path(os.getenv("ADE_UI_STATE_DB", "output/ade_ui_state.sqlite3"))
_LEGACY_JSON_PATH = Path("output/ade_order_candidates.json")
_LEGACY_OWNER_ID = "legacy-import"
_LOCK = threading.RLock()
_SCHEMA_READY = False
_SCHEMA_VERSION = 2
_MAX_CANDIDATES_PER_OWNER = 100
_HEALTH_CACHE_TTL_SECONDS = 30.0
_HEALTH_CACHE: tuple[float, dict[str, Any]] | None = None


class OrderCandidateStoreError(RuntimeError):
    pass


def _utc_now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def _connect() -> sqlite3.Connection:
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    except Exception as exc:  # pragma: no cover - surfaced to UI
        raise OrderCandidateStoreError(f"주문후보 DB 연결 실패: {exc}") from exc


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _read_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()
    if not row:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES('schema_version', ?)",
        (str(version),),
    )


def _migrate_schema(conn: sqlite3.Connection) -> None:
    version = _read_schema_version(conn)
    if version < 1:
        _set_schema_version(conn, 1)
        version = 1
    if version < 2:
        columns = _column_names(conn, "order_candidates")
        if "added_at_epoch" not in columns:
            conn.execute("ALTER TABLE order_candidates ADD COLUMN added_at_epoch REAL")
        if "last_selected_at_epoch" not in columns:
            conn.execute("ALTER TABLE order_candidates ADD COLUMN last_selected_at_epoch REAL")
        conn.execute(
            "UPDATE order_candidates SET added_at_epoch=COALESCE(added_at_epoch, strftime('%s', added_at))"
        )
        conn.execute(
            "UPDATE order_candidates SET last_selected_at_epoch=COALESCE(last_selected_at_epoch, strftime('%s', last_selected_at)) WHERE last_selected_at IS NOT NULL"
        )
        _set_schema_version(conn, 2)


def _ensure_schema() -> None:
    global _SCHEMA_READY
    with _LOCK:
        if _SCHEMA_READY:
            return
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS order_candidates (
                    owner_id TEXT NOT NULL,
                    market TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    last_selected_at TEXT,
                    added_at_epoch REAL,
                    last_selected_at_epoch REAL,
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
            _migrate_schema(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_order_candidates_owner_activity ON order_candidates(owner_id, COALESCE(last_selected_at_epoch, added_at_epoch) DESC)"
            )
            conn.commit()
        _SCHEMA_READY = True


def _migrate_legacy_once() -> None:
    _ensure_schema()
    with _LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        done = conn.execute("SELECT value FROM app_meta WHERE key='legacy_candidates_migrated'").fetchone()
        if done:
            conn.rollback()
            return
        rows: list[dict[str, Any]] = []
        if _LEGACY_JSON_PATH.exists():
            try:
                payload = json.loads(_LEGACY_JSON_PATH.read_text(encoding="utf-8"))
                rows = payload if isinstance(payload, list) else []
            except Exception as exc:
                conn.rollback()
                raise OrderCandidateStoreError(f"기존 주문후보 JSON 읽기 실패: {exc}") from exc
        for row in rows:
            market = str(row.get("market") or "").strip()
            ticker = str(row.get("ticker") or "").strip()
            symbol = str(row.get("symbol") or ticker).strip()
            if not market or not ticker:
                continue
            added_at = str(row.get("added_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"))
            try:
                added_epoch = datetime.fromisoformat(added_at).timestamp()
            except ValueError:
                added_epoch = _utc_now_epoch()
            conn.execute(
                """
                INSERT INTO order_candidates(owner_id, market, ticker, symbol, added_at, added_at_epoch)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_id, market, ticker) DO UPDATE SET
                    symbol=excluded.symbol,
                    added_at=excluded.added_at,
                    added_at_epoch=excluded.added_at_epoch
                """,
                (_LEGACY_OWNER_ID, market, ticker, symbol, added_at, added_epoch),
            )
        conn.execute(
            "INSERT OR REPLACE INTO app_meta(key, value) VALUES('legacy_candidates_migrated', ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
        )
        conn.commit()


def upsert_candidate(owner_id: str, market: str, ticker: str, symbol: str) -> None:
    _migrate_legacy_once()
    added_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    added_epoch = _utc_now_epoch()
    with _LOCK, _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO order_candidates(owner_id, market, ticker, symbol, added_at, added_at_epoch)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_id, market, ticker) DO UPDATE SET
                symbol=excluded.symbol,
                added_at=excluded.added_at,
                added_at_epoch=excluded.added_at_epoch
            """,
            (owner_id, market, ticker, symbol, added_at, added_epoch),
        )
        conn.execute(
            """
            DELETE FROM order_candidates
            WHERE owner_id=? AND rowid NOT IN (
                SELECT rowid FROM order_candidates
                WHERE owner_id=?
                ORDER BY COALESCE(last_selected_at_epoch, added_at_epoch) DESC, added_at_epoch DESC
                LIMIT ?
            )
            """,
            (owner_id, owner_id, _MAX_CANDIDATES_PER_OWNER),
        )
        conn.commit()


def list_candidates(owner_id: str, market: str | None = None) -> list[dict[str, Any]]:
    _migrate_legacy_once()
    sql = "SELECT market, ticker, symbol, added_at, last_selected_at FROM order_candidates WHERE owner_id=?"
    params: list[Any] = [owner_id]
    if market:
        sql += " AND market=?"
        params.append(market)
    sql += " ORDER BY COALESCE(last_selected_at_epoch, added_at_epoch) DESC, added_at_epoch DESC"
    with _LOCK, _connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def list_legacy_candidates(market: str | None = None) -> list[dict[str, Any]]:
    return list_candidates(_LEGACY_OWNER_ID, market)


def import_legacy_candidates(owner_id: str, market: str | None = None) -> int:
    rows = list_legacy_candidates(market)
    imported = 0
    for row in rows:
        upsert_candidate(owner_id, str(row["market"]), str(row["ticker"]), str(row["symbol"]))
        imported += 1
    return imported


def mark_selected(owner_id: str, market: str, ticker: str) -> None:
    _migrate_legacy_once()
    selected_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    selected_epoch = _utc_now_epoch()
    with _LOCK, _connect() as conn:
        conn.execute(
            "UPDATE order_candidates SET last_selected_at=?, last_selected_at_epoch=? WHERE owner_id=? AND market=? AND ticker=?",
            (selected_at, selected_epoch, owner_id, market, ticker),
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


def store_health(*, refresh: bool = False) -> dict[str, Any]:
    global _HEALTH_CACHE
    now = time.monotonic()
    with _LOCK:
        if not refresh and _HEALTH_CACHE and now - _HEALTH_CACHE[0] <= _HEALTH_CACHE_TTL_SECONDS:
            return dict(_HEALTH_CACHE[1])
    try:
        _ensure_schema()
        with _connect() as conn:
            conn.execute("SELECT 1").fetchone()
            version = _read_schema_version(conn)
        result = {
            "status": "정상",
            "path": str(_DB_PATH),
            "writable": os.access(_DB_PATH.parent, os.W_OK),
            "schema_version": version,
            "checked_at": time.time(),
        }
    except Exception as exc:
        result = {
            "status": "오류",
            "path": str(_DB_PATH),
            "error": str(exc),
            "writable": False,
            "schema_version": None,
            "checked_at": time.time(),
        }
    with _LOCK:
        _HEALTH_CACHE = (time.monotonic(), dict(result))
    return result
