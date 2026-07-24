from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from broker.base import BrokerOrder
from trading.order_service import TradingOrderService


class ScheduledOrderService:
    """Persist and activate scheduled orders without bypassing user approval.

    Supported trigger types:
    - TIME: activate once a due time is reached.
    - PRICE_LE: activate when the current price is less than or equal to trigger_price.
    - PRICE_GE: activate when the current price is greater than or equal to trigger_price.

    Recurrence is optional. Recurring schedules are advanced after activation and remain
    scheduled; each occurrence creates a normal PENDING_APPROVAL order request.
    """

    ACTIVE_STATUSES = {"SCHEDULED", "RETRY_WAIT"}
    TRIGGER_TYPES = {"TIME", "PRICE_LE", "PRICE_GE"}
    RECURRENCES = {"NONE", "DAILY", "WEEKLY", "MONTHLY"}

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
                updated_at TEXT,
                scheduled_at TEXT,
                next_check_at TEXT,
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
                trigger_type TEXT NOT NULL DEFAULT 'TIME',
                trigger_price REAL,
                recurrence TEXT NOT NULL DEFAULT 'NONE',
                recurrence_end_at TEXT,
                max_activations INTEGER,
                activation_count INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                status TEXT NOT NULL,
                generated_request_id TEXT,
                last_trigger_price REAL,
                error_message TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_scheduled_order_due
                ON scheduled_order_requests(status, scheduled_at, next_check_at);
            CREATE INDEX IF NOT EXISTS idx_scheduled_order_trigger
                ON scheduled_order_requests(status, trigger_type, market, ticker);
            """
        )
        columns = {
            str(row[1]) for row in self.conn.execute("PRAGMA table_info(scheduled_order_requests)").fetchall()
        }
        migrations = {
            "updated_at": "ALTER TABLE scheduled_order_requests ADD COLUMN updated_at TEXT",
            "next_check_at": "ALTER TABLE scheduled_order_requests ADD COLUMN next_check_at TEXT",
            "trigger_type": "ALTER TABLE scheduled_order_requests ADD COLUMN trigger_type TEXT NOT NULL DEFAULT 'TIME'",
            "trigger_price": "ALTER TABLE scheduled_order_requests ADD COLUMN trigger_price REAL",
            "recurrence": "ALTER TABLE scheduled_order_requests ADD COLUMN recurrence TEXT NOT NULL DEFAULT 'NONE'",
            "recurrence_end_at": "ALTER TABLE scheduled_order_requests ADD COLUMN recurrence_end_at TEXT",
            "max_activations": "ALTER TABLE scheduled_order_requests ADD COLUMN max_activations INTEGER",
            "activation_count": "ALTER TABLE scheduled_order_requests ADD COLUMN activation_count INTEGER NOT NULL DEFAULT 0",
            "retry_count": "ALTER TABLE scheduled_order_requests ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
            "max_retries": "ALTER TABLE scheduled_order_requests ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 3",
            "last_trigger_price": "ALTER TABLE scheduled_order_requests ADD COLUMN last_trigger_price REAL",
        }
        for column, sql in migrations.items():
            if column not in columns:
                self.conn.execute(sql)
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
        scheduled_at: str | datetime | None = None,
        order_type: str = "MARKET",
        limit_price: float | None = None,
        target_return: float | None = None,
        stop_return: float | None = None,
        source_run_id: str | None = None,
        source_rank: int | None = None,
        market: str = "kr",
        trigger_type: str = "TIME",
        trigger_price: float | None = None,
        recurrence: str = "NONE",
        recurrence_end_at: str | datetime | None = None,
        max_activations: int | None = None,
        max_retries: int = 3,
    ) -> str:
        market = str(market).lower()
        trigger_type = str(trigger_type).upper()
        recurrence = str(recurrence).upper()
        if trigger_type not in self.TRIGGER_TYPES:
            raise ValueError(f"지원하지 않는 예약 조건입니다: {trigger_type}")
        if recurrence not in self.RECURRENCES:
            raise ValueError(f"지원하지 않는 반복 주기입니다: {recurrence}")
        if trigger_type != "TIME" and (trigger_price is None or float(trigger_price) <= 0):
            raise ValueError("가격 조건 예약은 0보다 큰 기준 가격이 필요합니다.")

        order = BrokerOrder(
            market=market,
            ticker=ticker,
            side=side.upper(),
            quantity=int(quantity),
            order_type=order_type.upper(),
            limit_price=limit_price,
            dry_run=False,
        )
        order.validate()

        due = self._as_utc(scheduled_at) if scheduled_at is not None else None
        if trigger_type == "TIME":
            if due is None:
                raise ValueError("시간 예약은 예약 시각이 필요합니다.")
            if due <= datetime.now(timezone.utc):
                raise ValueError("예약 시각은 현재보다 이후여야 합니다.")
        elif due is not None and due <= datetime.now(timezone.utc):
            raise ValueError("가격 감시 시작 시각은 현재보다 이후여야 합니다.")

        recurrence_end = self._as_utc(recurrence_end_at) if recurrence_end_at is not None else None
        if recurrence_end and due and recurrence_end < due:
            raise ValueError("반복 종료 시각은 최초 예약 시각 이후여야 합니다.")
        if max_activations is not None and int(max_activations) < 1:
            raise ValueError("최대 실행 횟수는 1 이상이어야 합니다.")

        due_text = due.isoformat(timespec="seconds") if due else None
        duplicate = self.conn.execute(
            "SELECT schedule_id FROM scheduled_order_requests WHERE market=? AND ticker=? AND side=? AND quantity=? "
            "AND order_type=? AND COALESCE(limit_price, -1)=COALESCE(?, -1) "
            "AND trigger_type=? AND COALESCE(trigger_price, -1)=COALESCE(?, -1) "
            "AND COALESCE(scheduled_at, '')=COALESCE(?, '') AND status IN ('SCHEDULED','RETRY_WAIT') LIMIT 1",
            (
                market, ticker, order.side, order.quantity, order.order_type, order.limit_price,
                trigger_type, trigger_price, due_text,
            ),
        ).fetchone()
        if duplicate:
            raise ValueError(f"동일한 예약주문이 이미 있습니다: {duplicate['schedule_id']}")

        now = self._now()
        schedule_id = f"SCH-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        self.conn.execute(
            """
            INSERT INTO scheduled_order_requests(
                schedule_id, created_at, updated_at, scheduled_at, next_check_at,
                market, ticker, name, side, quantity, order_type, limit_price,
                target_return, stop_return, source_run_id, source_rank,
                trigger_type, trigger_price, recurrence, recurrence_end_at,
                max_activations, activation_count, retry_count, max_retries, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, 'SCHEDULED')
            """,
            (
                schedule_id, now, now, due_text, due_text, market, ticker, name,
                order.side, order.quantity, order.order_type, order.limit_price,
                target_return, stop_return, source_run_id, source_rank,
                trigger_type, float(trigger_price) if trigger_price is not None else None,
                recurrence, recurrence_end.isoformat(timespec="seconds") if recurrence_end else None,
                int(max_activations) if max_activations is not None else None,
                max(0, int(max_retries)),
            ),
        )
        self.conn.commit()
        return schedule_id

    def update_schedule(self, schedule_id: str, **changes: object) -> None:
        allowed = {
            "scheduled_at", "trigger_type", "trigger_price", "quantity", "order_type",
            "limit_price", "target_return", "stop_return", "recurrence",
            "recurrence_end_at", "max_activations", "max_retries",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"수정할 수 없는 필드입니다: {', '.join(sorted(unknown))}")
        row = self.conn.execute(
            "SELECT * FROM scheduled_order_requests WHERE schedule_id=?", (schedule_id,)
        ).fetchone()
        if row is None:
            raise ValueError("예약주문을 찾을 수 없습니다.")
        if row["status"] not in self.ACTIVE_STATUSES:
            raise ValueError("대기 중인 예약주문만 수정할 수 있습니다.")

        values = dict(row)
        values.update(changes)
        trigger_type = str(values.get("trigger_type") or "TIME").upper()
        recurrence = str(values.get("recurrence") or "NONE").upper()
        if trigger_type not in self.TRIGGER_TYPES or recurrence not in self.RECURRENCES:
            raise ValueError("예약 조건 또는 반복 주기가 올바르지 않습니다.")
        if trigger_type != "TIME" and float(values.get("trigger_price") or 0) <= 0:
            raise ValueError("가격 조건 예약은 0보다 큰 기준 가격이 필요합니다.")
        due = self._as_utc(values["scheduled_at"]) if values.get("scheduled_at") else None
        if trigger_type == "TIME" and (due is None or due <= datetime.now(timezone.utc)):
            raise ValueError("시간 예약은 현재보다 이후 시각이 필요합니다.")
        recurrence_end = self._as_utc(values["recurrence_end_at"]) if values.get("recurrence_end_at") else None

        order = BrokerOrder(
            market=str(row["market"]), ticker=str(row["ticker"]), side=str(row["side"]),
            quantity=int(values["quantity"]), order_type=str(values["order_type"]),
            limit_price=values.get("limit_price"), dry_run=False,
        )
        order.validate()
        self.conn.execute(
            """
            UPDATE scheduled_order_requests SET updated_at=?, scheduled_at=?, next_check_at=?,
                trigger_type=?, trigger_price=?, quantity=?, order_type=?, limit_price=?,
                target_return=?, stop_return=?, recurrence=?, recurrence_end_at=?,
                max_activations=?, max_retries=?, retry_count=0, error_message=NULL, status='SCHEDULED'
            WHERE schedule_id=?
            """,
            (
                self._now(), due.isoformat(timespec="seconds") if due else None,
                due.isoformat(timespec="seconds") if due else None, trigger_type,
                float(values.get("trigger_price")) if values.get("trigger_price") is not None else None,
                order.quantity, order.order_type, order.limit_price,
                values.get("target_return"), values.get("stop_return"), recurrence,
                recurrence_end.isoformat(timespec="seconds") if recurrence_end else None,
                int(values["max_activations"]) if values.get("max_activations") is not None else None,
                max(0, int(values.get("max_retries") or 0)), schedule_id,
            ),
        )
        self.conn.commit()

    def activate_due(self, quote_provider=None) -> list[dict[str, object]]:
        now = datetime.now(timezone.utc)
        rows = self.conn.execute(
            "SELECT * FROM scheduled_order_requests WHERE status IN ('SCHEDULED','RETRY_WAIT') "
            "ORDER BY COALESCE(scheduled_at, next_check_at, created_at)"
        ).fetchall()
        activated: list[dict[str, object]] = []
        order_service = TradingOrderService(self.db_path)
        try:
            for row in rows:
                if not self._is_due(dict(row), now, quote_provider):
                    continue
                cursor = self.conn.execute(
                    "UPDATE scheduled_order_requests SET status='ACTIVATING', updated_at=? "
                    "WHERE schedule_id=? AND status IN ('SCHEDULED','RETRY_WAIT')",
                    (self._now(), row["schedule_id"]),
                )
                self.conn.commit()
                if cursor.rowcount != 1:
                    continue
                try:
                    request_id = order_service.create_request(
                        ticker=str(row["ticker"]), name=row["name"], side=str(row["side"]),
                        quantity=int(row["quantity"]), order_type=str(row["order_type"]),
                        limit_price=row["limit_price"], target_return=row["target_return"],
                        stop_return=row["stop_return"], source_run_id=row["source_run_id"],
                        source_rank=row["source_rank"],
                    )
                    next_at = self._next_occurrence(dict(row), now)
                    activation_count = int(row["activation_count"] or 0) + 1
                    should_repeat = next_at is not None and not self._recurrence_complete(dict(row), activation_count, next_at)
                    status = "SCHEDULED" if should_repeat else "ACTIVATED"
                    self.conn.execute(
                        """
                        UPDATE scheduled_order_requests SET status=?, activated_at=?, updated_at=?,
                            generated_request_id=?, activation_count=?, retry_count=0,
                            scheduled_at=?, next_check_at=?, error_message=NULL
                        WHERE schedule_id=?
                        """,
                        (
                            status, self._now(), self._now(), request_id, activation_count,
                            next_at.isoformat(timespec="seconds") if should_repeat else row["scheduled_at"],
                            next_at.isoformat(timespec="seconds") if should_repeat else None,
                            row["schedule_id"],
                        ),
                    )
                    activated.append({"schedule_id": row["schedule_id"], "request_id": request_id})
                except Exception as exc:
                    retry_count = int(row["retry_count"] or 0) + 1
                    max_retries = max(0, int(row["max_retries"] or 0))
                    if retry_count <= max_retries:
                        delay_minutes = min(60, 2 ** (retry_count - 1) * 5)
                        next_check = now + timedelta(minutes=delay_minutes)
                        status = "RETRY_WAIT"
                    else:
                        next_check = None
                        status = "FAILED"
                    self.conn.execute(
                        "UPDATE scheduled_order_requests SET status=?, updated_at=?, retry_count=?, "
                        "next_check_at=?, error_message=? WHERE schedule_id=?",
                        (
                            status, self._now(), retry_count,
                            next_check.isoformat(timespec="seconds") if next_check else None,
                            str(exc), row["schedule_id"],
                        ),
                    )
                self.conn.commit()
        finally:
            order_service.close()
        return activated

    def list_schedules(self, limit: int = 500) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT * FROM scheduled_order_requests ORDER BY created_at DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(row) for row in rows]

    def pending_schedules(self, limit: int = 500) -> list[dict[str, object]]:
        rows = self.conn.execute(
            "SELECT * FROM scheduled_order_requests WHERE status IN ('SCHEDULED','RETRY_WAIT') "
            "ORDER BY COALESCE(scheduled_at, next_check_at, created_at) LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(row) for row in rows]

    def cancel_schedule(self, schedule_id: str) -> None:
        cursor = self.conn.execute(
            "UPDATE scheduled_order_requests SET status='CANCELLED', cancelled_at=?, updated_at=? "
            "WHERE schedule_id=? AND status IN ('SCHEDULED','RETRY_WAIT')",
            (self._now(), self._now(), schedule_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            raise ValueError("취소 가능한 예약주문이 아닙니다.")

    def retry_schedule(self, schedule_id: str) -> None:
        cursor = self.conn.execute(
            "UPDATE scheduled_order_requests SET status='SCHEDULED', retry_count=0, error_message=NULL, "
            "next_check_at=?, updated_at=? WHERE schedule_id=? AND status='FAILED'",
            (self._now(), self._now(), schedule_id),
        )
        self.conn.commit()
        if cursor.rowcount != 1:
            raise ValueError("재시도 가능한 실패 예약주문이 아닙니다.")

    def _is_due(self, row: dict[str, object], now: datetime, quote_provider) -> bool:
        next_check = row.get("next_check_at")
        if next_check and self._as_utc(str(next_check)) > now:
            return False
        scheduled_at = row.get("scheduled_at")
        if scheduled_at and self._as_utc(str(scheduled_at)) > now:
            return False
        trigger_type = str(row.get("trigger_type") or "TIME")
        if trigger_type == "TIME":
            return True
        price = self._current_price(str(row["market"]), str(row["ticker"]), quote_provider)
        self.conn.execute(
            "UPDATE scheduled_order_requests SET last_trigger_price=?, updated_at=? WHERE schedule_id=?",
            (price, self._now(), row["schedule_id"]),
        )
        self.conn.commit()
        trigger_price = float(row.get("trigger_price") or 0.0)
        return price <= trigger_price if trigger_type == "PRICE_LE" else price >= trigger_price

    def _current_price(self, market: str, ticker: str, quote_provider) -> float:
        if quote_provider is not None:
            quote = quote_provider(market, ticker)
        elif market == "kr":
            from broker.kis_market_data import kis_market_data_from_env
            quote = kis_market_data_from_env().get_current_quote(ticker)
        else:
            raise ValueError("미국 가격 조건 감시에는 quote_provider가 필요합니다.")
        price = float(quote.get("current_price") or quote.get("price") or 0.0)
        if price <= 0:
            raise ValueError("현재가를 확인할 수 없습니다.")
        return price

    def _next_occurrence(self, row: dict[str, object], now: datetime) -> datetime | None:
        recurrence = str(row.get("recurrence") or "NONE")
        if recurrence == "NONE":
            return None
        base = self._as_utc(str(row.get("scheduled_at") or now.isoformat()))
        while base <= now:
            if recurrence == "DAILY":
                base += timedelta(days=1)
            elif recurrence == "WEEKLY":
                base += timedelta(weeks=1)
            else:
                local = base.astimezone(ZoneInfo("Asia/Seoul"))
                month = local.month + 1
                year = local.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                day = min(local.day, self._days_in_month(year, month))
                base = local.replace(year=year, month=month, day=day).astimezone(timezone.utc)
        return base

    @staticmethod
    def _recurrence_complete(row: dict[str, object], activation_count: int, next_at: datetime) -> bool:
        max_activations = row.get("max_activations")
        if max_activations is not None and activation_count >= int(max_activations):
            return True
        recurrence_end = row.get("recurrence_end_at")
        if recurrence_end and next_at > ScheduledOrderService._as_utc(str(recurrence_end)):
            return True
        return False

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        if month == 12:
            nxt = datetime(year + 1, 1, 1)
        else:
            nxt = datetime(year, month + 1, 1)
        return (nxt - timedelta(days=1)).day

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
            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return parsed.astimezone(timezone.utc)
