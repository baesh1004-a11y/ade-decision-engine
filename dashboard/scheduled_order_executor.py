from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from dashboard.standard_order_panel import _ensure_scheduled_schema, _scheduled_db_path


STATUS_PENDING = "PENDING"
STATUS_APPROVAL = "APPROVAL_PENDING"
STATUS_SUBMITTING = "SUBMITTING"
STATUS_EXECUTED = "EXECUTED"
STATUS_FAILED = "FAILED"
STATUS_CANCELLED = "CANCELLED"


def _now() -> datetime:
    return datetime.now()


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _next_execute_at(current: datetime, recurrence: str) -> datetime | None:
    recurrence = str(recurrence or "ONCE").upper()
    if recurrence == "DAILY":
        return current + timedelta(days=1)
    if recurrence == "WEEKLY":
        return current + timedelta(days=7)
    if recurrence == "MONTHLY":
        month = current.month + 1
        year = current.year
        if month > 12:
            month = 1
            year += 1
        day = min(current.day, 28)
        return current.replace(year=year, month=month, day=day)
    return None


def _load_due_orders(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM scheduled_orders WHERE status=? ORDER BY id",
        (STATUS_PENDING,),
    ).fetchall()
    return [dict(row) for row in rows]


def _trigger_met(order: dict[str, Any], current_price: float, now: datetime) -> bool:
    trigger = str(order.get("trigger_type") or "").upper()
    if trigger == "TIME":
        execute_at = _parse_datetime(order.get("execute_at"))
        return execute_at is not None and now >= execute_at
    trigger_price = float(order.get("trigger_price") or 0)
    if trigger == "PRICE_BELOW":
        return current_price > 0 and current_price <= trigger_price
    if trigger == "PRICE_ABOVE":
        return current_price > 0 and current_price >= trigger_price
    return False


def _mark_error(conn: sqlite3.Connection, order_id: int, message: str) -> None:
    conn.execute(
        "UPDATE scheduled_orders SET retry_count=retry_count+1, last_error=?, status=? WHERE id=?",
        (message[:500], STATUS_FAILED, int(order_id)),
    )


def run_scheduled_orders_once(
    *,
    quote_loader: Callable[[str], tuple[dict[str, Any] | None, str | None]],
    submitter: Callable[[str, str, int, str, float | None], tuple[bool, str]],
    require_approval: bool = False,
) -> dict[str, int]:
    """Evaluate all pending scheduled orders once.

    When require_approval is False, matched orders are sent to KIS immediately.
    When True, they transition to APPROVAL_PENDING without transmission.
    """
    _ensure_scheduled_schema()
    path: Path = _scheduled_db_path()
    stats = {"checked": 0, "triggered": 0, "executed": 0, "failed": 0, "approval_pending": 0}
    now = _now()

    with sqlite3.connect(path) as conn:
        orders = _load_due_orders(conn)
        for order in orders:
            stats["checked"] += 1
            ticker = str(order.get("ticker") or "")
            quote, quote_error = quote_loader(ticker)
            if quote_error:
                _mark_error(conn, int(order["id"]), f"현재가 조회 실패: {quote_error}")
                stats["failed"] += 1
                continue
            current_price = float((quote or {}).get("price") or 0)
            if not _trigger_met(order, current_price, now):
                continue

            stats["triggered"] += 1
            if require_approval:
                conn.execute(
                    "UPDATE scheduled_orders SET status=?, last_error=NULL WHERE id=?",
                    (STATUS_APPROVAL, int(order["id"])),
                )
                stats["approval_pending"] += 1
                continue

            conn.execute(
                "UPDATE scheduled_orders SET status=?, last_error=NULL WHERE id=?",
                (STATUS_SUBMITTING, int(order["id"])),
            )
            conn.commit()

            ok, message = submitter(
                ticker,
                str(order.get("side") or "매수"),
                int(order.get("quantity") or 0),
                str(order.get("order_type") or "MARKET"),
                float(order["limit_price"]) if order.get("limit_price") is not None else None,
            )

            if not ok:
                _mark_error(conn, int(order["id"]), message or "주문 전송 실패")
                stats["failed"] += 1
                continue

            recurrence = str(order.get("recurrence") or "ONCE").upper()
            current_execute_at = _parse_datetime(order.get("execute_at")) or now
            next_at = _next_execute_at(current_execute_at, recurrence)
            if next_at is None:
                conn.execute(
                    "UPDATE scheduled_orders SET status=?, last_error=NULL WHERE id=?",
                    (STATUS_EXECUTED, int(order["id"])),
                )
            else:
                conn.execute(
                    "UPDATE scheduled_orders SET status=?, execute_at=?, last_error=NULL WHERE id=?",
                    (STATUS_PENDING, next_at.isoformat(), int(order["id"])),
                )
            stats["executed"] += 1
        conn.commit()
    return stats
