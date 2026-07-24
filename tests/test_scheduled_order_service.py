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
        assert service.list_schedules()[0]["status"] == "CANCELLED"
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


def test_price_trigger_requires_positive_price(tmp_path):
    service = ScheduledOrderService(tmp_path / "market.db")
    try:
        with pytest.raises(ValueError, match="기준 가격"):
            service.create_schedule(
                ticker="005930",
                name="삼성전자",
                side="BUY",
                quantity=1,
                scheduled_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                trigger_type="PRICE_LE",
                trigger_price=0,
            )
    finally:
        service.close()


def test_price_trigger_is_evaluated(tmp_path, monkeypatch):
    service = ScheduledOrderService(tmp_path / "market.db")
    try:
        schedule_id = service.create_schedule(
            ticker="005930",
            name="삼성전자",
            side="BUY",
            quantity=1,
            scheduled_at=datetime.now(timezone.utc) + timedelta(seconds=1),
            trigger_type="PRICE_LE",
            trigger_price=70000,
        )
        row = service.list_schedules()[0]
        assert service._is_due(row, datetime.now(timezone.utc), lambda market, ticker: {"current_price": 69000}) is False
        service.conn.execute(
            "UPDATE scheduled_order_requests SET scheduled_at=? WHERE schedule_id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), schedule_id),
        )
        service.conn.commit()
        row = service.list_schedules()[0]
        assert service._is_due(row, datetime.now(timezone.utc), lambda market, ticker: {"current_price": 69000}) is True
    finally:
        service.close()


def test_update_schedule(tmp_path):
    service = ScheduledOrderService(tmp_path / "market.db")
    try:
        schedule_id = service.create_schedule(
            ticker="005930",
            name="삼성전자",
            side="BUY",
            quantity=1,
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        new_time = datetime.now(timezone.utc) + timedelta(hours=2)
        service.update_schedule(schedule_id, quantity=3, scheduled_at=new_time)
        row = service.list_schedules()[0]
        assert row["quantity"] == 3
        assert row["status"] == "SCHEDULED"
    finally:
        service.close()


def test_daily_recurrence_advances(tmp_path):
    service = ScheduledOrderService(tmp_path / "market.db")
    try:
        row = {
            "recurrence": "DAILY",
            "scheduled_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        }
        next_at = service._next_occurrence(row, datetime.now(timezone.utc))
        assert next_at is not None
        assert next_at > datetime.now(timezone.utc)
    finally:
        service.close()


def test_failed_schedule_can_be_retried(tmp_path):
    service = ScheduledOrderService(tmp_path / "market.db")
    try:
        schedule_id = service.create_schedule(
            ticker="005930",
            name="삼성전자",
            side="BUY",
            quantity=1,
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        service.conn.execute(
            "UPDATE scheduled_order_requests SET status='FAILED', error_message='test' WHERE schedule_id=?",
            (schedule_id,),
        )
        service.conn.commit()
        service.retry_schedule(schedule_id)
        row = service.list_schedules()[0]
        assert row["status"] == "SCHEDULED"
        assert row["retry_count"] == 0
        assert row["error_message"] is None
    finally:
        service.close()
