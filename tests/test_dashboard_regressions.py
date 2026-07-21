from __future__ import annotations

import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path

from ade_home import _count_sum, _latest_recommendation_count, _latest_validation_count, _portfolio_summary
from dashboard.trading_desk_app import _ai_confidence, _yahoo_tickers
from trading.order_service import TradingOrderService
from trading.us_order_service import USTradingOrderService


def test_yahoo_candidates_try_both_kr_markets_when_suffix_is_unknown() -> None:
    assert _yahoo_tickers("035720") == ["035720.KS", "035720.KQ"]
    assert _yahoo_tickers("035720.KQ") == ["035720.KQ"]


def test_ai_confidence_does_not_invent_missing_scores() -> None:
    score, level, _tone, _opinion, factors = _ai_confidence({}, None)

    assert score is None
    assert level == "계산 불가"
    assert all(value == "미확인" for _label, value, _signal in factors)


def test_latest_validation_count_uses_source_run_id(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE recommendation_runs(
            run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, status TEXT NOT NULL
        );
        CREATE TABLE final_decisions(
            source_run_id TEXT NOT NULL, ticker TEXT NOT NULL
        );
        INSERT INTO recommendation_runs VALUES ('old', '2026-01-01T09:00:00', 'COMPLETED');
        INSERT INTO recommendation_runs VALUES ('new', '2026-01-02T09:00:00', 'COMPLETED');
        INSERT INTO final_decisions VALUES ('old', 'AAA');
        INSERT INTO final_decisions VALUES ('old', 'BBB');
        INSERT INTO final_decisions VALUES ('new', 'CCC');
        """
    )
    conn.commit()
    conn.close()

    assert _latest_validation_count(path) == 1


def test_portfolio_summary_avoids_double_count_and_keeps_usd_separate(tmp_path: Path) -> None:
    kr_path = tmp_path / "kr.db"
    kr = sqlite3.connect(kr_path)
    kr.executescript(
        """
        CREATE TABLE positions(ticker TEXT, market_value REAL);
        CREATE TABLE account_summary(cash REAL, total_equity REAL);
        INSERT INTO positions VALUES ('005930', 700.0);
        INSERT INTO account_summary VALUES (300.0, 1000.0);
        """
    )
    kr.commit()
    kr.close()

    us_path = tmp_path / "us.db"
    us = sqlite3.connect(us_path)
    us.executescript(
        """
        CREATE TABLE us_position_snapshots(
            captured_at TEXT, ticker TEXT, evaluation_amount REAL, currency TEXT
        );
        INSERT INTO us_position_snapshots VALUES ('2026-01-01T09:00:00', 'OLD', 999.0, 'USD');
        INSERT INTO us_position_snapshots VALUES ('2026-01-02T09:00:00', 'AAPL', 120.0, 'USD');
        INSERT INTO us_position_snapshots VALUES ('2026-01-02T09:00:00', 'NVDA', 80.0, 'USD');
        """
    )
    us.commit()
    us.close()

    summary = _portfolio_summary(kr_path, us_path)

    assert summary.kr_holdings == 1
    assert summary.krw_value == 1000.0
    assert summary.krw_cash == 300.0
    assert summary.us_holdings == 2
    assert summary.usd_value == 200.0


def test_command_center_distinguishes_missing_db_from_zero(tmp_path: Path) -> None:
    assert _latest_recommendation_count(tmp_path / "missing.db") is None
    assert _count_sum(1, None) is None
    assert _count_sum(1, 2) == 3


def test_pending_approvals_are_not_hidden_by_recent_history(tmp_path: Path) -> None:
    service = TradingOrderService(tmp_path / "orders.db")
    try:
        old = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
        service.conn.execute(
            """INSERT INTO trade_order_requests(
                request_id, created_at, market, ticker, side, quantity,
                order_type, status
            ) VALUES ('pending-old', ?, 'kr', '005930', 'BUY', 1, 'MARKET', 'PENDING_APPROVAL')""",
            (old,),
        )
        for index in range(110):
            service.conn.execute(
                """INSERT INTO trade_order_requests(
                    request_id, created_at, market, ticker, side, quantity,
                    order_type, status
                ) VALUES (?, ?, 'kr', '000000', 'BUY', 1, 'MARKET', 'SENT')""",
                (f"sent-{index}", datetime.now().isoformat(timespec="seconds")),
            )
        service.conn.commit()

        assert [row["request_id"] for row in service.pending_approval_requests()] == ["pending-old"]
    finally:
        service.close()


def test_stale_pending_order_expires(tmp_path: Path) -> None:
    previous = os.environ.get("ADE_ORDER_REQUEST_TTL_MINUTES")
    os.environ["ADE_ORDER_REQUEST_TTL_MINUTES"] = "30"
    service = TradingOrderService(tmp_path / "orders.db")
    try:
        created_at = (datetime.now() - timedelta(minutes=31)).isoformat(timespec="seconds")
        service.conn.execute(
            """INSERT INTO trade_order_requests(
                request_id, created_at, market, ticker, side, quantity,
                order_type, status
            ) VALUES ('expired', ?, 'kr', '005930', 'BUY', 1, 'MARKET', 'PENDING_APPROVAL')""",
            (created_at,),
        )
        service.conn.commit()

        assert service.expire_stale_requests() == 1
        status = service.conn.execute(
            "SELECT status FROM trade_order_requests WHERE request_id='expired'"
        ).fetchone()[0]
        assert status == "EXPIRED"
    finally:
        service.close()
        if previous is None:
            os.environ.pop("ADE_ORDER_REQUEST_TTL_MINUTES", None)
        else:
            os.environ["ADE_ORDER_REQUEST_TTL_MINUTES"] = previous


def test_execution_event_keys_are_stable() -> None:
    event = {
        "order_id": "123",
        "ticker": "005930",
        "side": "BUY",
        "ordered_quantity": 2,
        "filled_quantity": 2,
        "filled_price": 70000,
        "status": "FILLED",
        "executed_at": "2026-07-21T10:00:00",
    }
    assert TradingOrderService._execution_event_key(event) == TradingOrderService._execution_event_key(dict(event))
    assert USTradingOrderService._execution_event_key(event) == USTradingOrderService._execution_event_key(dict(event))
