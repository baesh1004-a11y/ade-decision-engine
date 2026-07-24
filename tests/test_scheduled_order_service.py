from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading.scheduled_order_service import ScheduledOrderService


def test_create_and_cancel_schedule(tmp_path):
    service = ScheduledOrderService(tmp_path / "market.db")
    try:
        schedule_id = service.create_schedule(
            ticker="005930",
            name="삼성전자",
            side="BUY",
            quantity=1,
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
            order_type="LIMIT",
            limit_price=70000,
        )
        pending = service.pending_schedules()
        assert [row["schedule_id"] for row in pending] == [schedule_id]
        assert pending[0]["status"] == "SCHEDULED"

        service.cancel_schedule(schedule_id)
        assert service.pending_schedules() == []
        history = service.list_schedules()
        assert history[0]["status"] == "CANCELLED"
    finally:
        service.close()


def test_schedule_requires_future_time(tmp_path):
    service = ScheduledOrderService(tmp_path / "market.db")
    try:
        with pytest.raises(ValueError, match="현재보다 이후"):
            service.create_schedule(
                ticker="005930",
                name="삼성전자",
                side="BUY",
                quantity=1,
                scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
    finally:
        service.close()


def test_duplicate_schedule_is_rejected(tmp_path):
    service = ScheduledOrderService(tmp_path / "market.db")
    try:
        due = datetime.now(timezone.utc) + timedelta(hours=1)
        kwargs = dict(
            ticker="005930",
            name="삼성전자",
            side="BUY",
            quantity=1,
            scheduled_at=due,
            order_type="LIMIT",
            limit_price=70000,
        )
        service.create_schedule(**kwargs)
        with pytest.raises(ValueError, match="동일한 예약주문"):
            service.create_schedule(**kwargs)
    finally:
        service.close()
