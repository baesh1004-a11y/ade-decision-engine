from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RecommendationRunContext:
    run_id: str
    market: str
    started_at: str | None
    finished_at: str | None
    run_type: str | None
    recommendation_count: int
    recommendations: list[dict[str, Any]]
    validations: dict[str, dict[str, Any]]
    current_orders: list[dict[str, Any]]
    other_pending_orders: int


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def completed_runs(
    conn: sqlite3.Connection,
    market: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return completed recommendation runs that actually contain recommendations."""
    if not _table_exists(conn, "recommendation_runs") or not _table_exists(conn, "daily_recommendations"):
        return []
    rows = conn.execute(
        """
        SELECT
            r.*,
            COUNT(d.rowid) AS recommendation_count
        FROM recommendation_runs r
        JOIN daily_recommendations d
          ON d.run_id=r.run_id
         AND d.market=?
        WHERE r.status='COMPLETED'
        GROUP BY r.run_id
        ORDER BY COALESCE(r.finished_at, r.started_at) DESC, r.started_at DESC
        LIMIT ?
        """,
        (market, max(1, int(limit))),
    ).fetchall()
    return [dict(row) for row in rows]


def completed_run_by_id(
    conn: sqlite3.Connection,
    market: str,
    run_id: str,
) -> dict[str, Any] | None:
    if not run_id:
        return None
    if not _table_exists(conn, "recommendation_runs") or not _table_exists(conn, "daily_recommendations"):
        return None
    row = conn.execute(
        """
        SELECT r.*
        FROM recommendation_runs r
        WHERE r.run_id=?
          AND r.status='COMPLETED'
          AND EXISTS(
              SELECT 1 FROM daily_recommendations d
              WHERE d.run_id=r.run_id AND d.market=?
          )
        LIMIT 1
        """,
        (run_id, market),
    ).fetchone()
    return dict(row) if row else None


def latest_completed_run(conn: sqlite3.Connection, market: str) -> dict[str, Any] | None:
    runs = completed_runs(conn, market, limit=1)
    return runs[0] if runs else None


def recommendations_for_run(
    conn: sqlite3.Connection, run_id: str, market: str, limit: int = 50
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM daily_recommendations
        WHERE run_id=? AND market=?
        ORDER BY rank_no
        LIMIT ?
        """,
        (run_id, market, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def validations_for_run(conn: sqlite3.Connection, run_id: str) -> dict[str, dict[str, Any]]:
    if not _table_exists(conn, "final_decisions"):
        return {}
    rows = conn.execute(
        "SELECT * FROM final_decisions WHERE source_run_id=? ORDER BY rank_no",
        (run_id,),
    ).fetchall()
    return {str(row["ticker"]): dict(row) for row in rows}


def orders_for_run(conn: sqlite3.Connection, run_id: str) -> tuple[list[dict[str, Any]], int]:
    if not _table_exists(conn, "trade_order_requests"):
        return [], 0
    pending_statuses = ("PENDING_APPROVAL", "PENDING", "READY", "APPROVED")
    placeholders = ",".join("?" for _ in pending_statuses)
    rows = conn.execute(
        f"""
        SELECT * FROM trade_order_requests
        WHERE source_run_id=? AND status IN ({placeholders})
        ORDER BY created_at DESC
        """,
        (run_id, *pending_statuses),
    ).fetchall()
    other = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM trade_order_requests
        WHERE COALESCE(source_run_id, '')<>? AND status IN ({placeholders})
        """,
        (run_id, *pending_statuses),
    ).fetchone()
    return [dict(row) for row in rows], int(other["count"] or 0)


def load_run_context(
    conn: sqlite3.Connection,
    market: str,
    run_id: str,
    limit: int = 50,
) -> RecommendationRunContext | None:
    run = completed_run_by_id(conn, market, run_id)
    if run is None:
        return None
    recommendations = recommendations_for_run(conn, run_id, market, limit)
    validations = validations_for_run(conn, run_id)
    current_orders, other_pending = orders_for_run(conn, run_id)
    return RecommendationRunContext(
        run_id=run_id,
        market=market,
        started_at=run.get("started_at"),
        finished_at=run.get("finished_at"),
        run_type=run.get("run_type"),
        recommendation_count=len(recommendations),
        recommendations=recommendations,
        validations=validations,
        current_orders=current_orders,
        other_pending_orders=other_pending,
    )


def load_latest_context(
    conn: sqlite3.Connection, market: str, limit: int = 50
) -> RecommendationRunContext | None:
    run = latest_completed_run(conn, market)
    if run is None:
        return None
    return load_run_context(conn, market, str(run["run_id"]), limit)
