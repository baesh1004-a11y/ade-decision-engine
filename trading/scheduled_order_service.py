from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from broker.base import BrokerOrder
from trading.order_service import TradingOrderService


class ScheduledOrderService:
    """Create and activate time-based scheduled orders.

    Scheduled orders never go directly to KIS. When due, they are converted into
    the existing PENDING_APPROVAL order workflow and still require explicit user
    approval before transmission.
    """

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.initialize()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scheduled_order_requests (
                schedule_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                activated_at TEXT,
                cancelled_at TEXT,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                order_type TEXT NOT NULL,
                limit_price REAL,
                target_return REAL,
                stop_return REAL,
                source_run_id TEXT,
                source_rank INTEGER,
                status TEXT NOT NULL,
                generated_request_id TEXT,
                error_message TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_scheduled_order_due
                ON scheduled_order_requests(status, scheduled_at);
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def create_schedule(
        self,
        *,
        ticker: str,
        name: str | None,
        side: str,
        quantity: int,
        scheduled_at: str | datetime,
        order_type: str = "MARKET",
        limit_price: float | None = None,
        target_return: float | None = None,
        stop_return: float | None = None,
        source_run_id: str | None = None,
        source_rank: int | None = None,
    ) -> str:
        order = BrokerOrder(
            market="kr",
            ticker=ticker,
            side=side.upper(),
            quantity=int(quantity),
            order_type=order_type.upper(),
            limit_price=limit_price,
            dry_run=False,
        )
        order.validate()
        due = self._as_utc(scheduled_at)
        if due <= datetime.now(timezone.utc):
            raise ValueError("예약 시각은 현재보다 이후여야 합니다.")

        duplicate = self.conn.execute(
            "SELECT schedule_id FROM scheduled_order_requests WHERE ticker=? AND side=? AND quantity=? "
            "AND order_type=? AND COALESCE(limit_price, -1)=COALESCE(?, -1) "
            "AND scheduled_at=? AND status='SCHEDULED' LIMIT 1",
            (ticker, order.side, order.quantity, order.order_type, order.limit_price, due.isoformat(timespec="seconds")),
        ).fetchone()
        if duplicate:
            raise ValueError(f"동일한 예약주문이 이미 있습니다: {duplicate['schedule_id']}")

        schedule_id = f"SCH-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        self.conn.execute(
            """
            INSERT INTO scheduled_order_requests(
                schedule_id, created_at, scheduled_at, market, ticker, name,
                side, quantity, order_type, limit_price, target_return,
                stop_return, source_run_id, source_rank, status
            ) VALUES (?, ?, ?, 'kr', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SCHEDULED')
            """,
            (
                schedule_id,
                self._now(),
                due.isoformat(timespec="seconds"),
                ticker,
                name,
                order.side,
                order.quantity,
                order.order_type,
                order.limit_price,
                target_return,
                stop_return,
                source_run_id,
                source_rank,
            ),
        )
        self.conn.commit()
        return schedule_id

    def activate_due(self) -> list[dict[str, object]]:
        now = self._now()
        rows = self.conn.execute(
            "SELECT * FROM scheduled_order_requests "
            "WHERE status='SCHEDULED' AND scheduled_at<=? ORDER BY scheduled_at",
            (now,),
        ).fetchall()
        if not rows:
            return []

        order_service = TradingOrderService(self.db_path)
        activated: list[dict[str, object]] = []
        try:
            for row in rows:
                cursor = self.conn.execute(
                    "UPDATE scheduled_order_requests SET status='ACTIVATING' "
                    "WHERE schedule_id=? AND status='SCHEDULED'",
                    (row["schedule_id"],),
                )
                self.conn.commit()
                if cursor.rowcount != 1:
                    continue
                try:
                    request_id = order_service.create_request(
                        ticker=str(row["ticker"]),
                        name=row["name"],
                        side=str(row["side"]),
                        quantity=int(row["quantity"]),
                        order_type=str(row["order_type"]),
                        limit_price=row["limit_price"],
                        target_return=row["target_return"],
                        stop_return=row["stop_return"],
                        source_run_id=row["source_run_id"],
                        source_rank=row["source_rank"],
                    )
                    self.conn.execute(
                        "UPDATE scheduled_order_requests SET status='ACTIVATED', activated_at=?, "
                        "generated_request_id=?, error_message=NULL WHERE schedule_id=?",
                        (self._now(), request_id, row["schedule_id"]),
                    )
                    activated.append({"schedule_id": row["schedule_id"], "request_id": request_id})
                except Exception as exc:
                    self.conn.execute(
                        "UPDATE scheduled_order_requests SET status='FAILED', error_message=? WHERE schedule_id=?",
                        (str(exc), row["schedule_id"]),
                    )
                self.conn.commit()
        finally:
            order_service.close()
        return activated

    def list_schedules(self, limit: int = 200) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT * FROM scheduled_order_requests ORDER BY created_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    def pending_schedules(self, limit: int = 200) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT * FROM scheduled_order_requests WHERE status='SCHEDULED' "
            "ORDER BY scheduled_at LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    def cancel_schedule(self, schedule_id: str) -> None:
        cursor = self.conn.execute(
            "UPDATE scheduled_order_requests SET status='CANCELLED', cancelled_at=? "
            "WHERE schedule_id=? AND status='SCHEDULED'",
            (self._now(), schedule_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            raise ValueError("취소 가능한 예약주문이 아닙니다.")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _as_utc(value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            from zoneinfo import ZoneInfo

            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return parsed.astimezone(timezone.utc)
