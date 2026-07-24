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


def test_duplicate_open_order_request_is_rejected(tmp_path: Path) -> None:
    service = TradingOrderService(tmp_path / "orders.db")
    try:
        first = service.create_request(ticker="005930", name="삼성전자", side="BUY", quantity=1)
        try:
            service.create_request(ticker="005930", name="삼성전자", side="BUY", quantity=1)
        except ValueError as exc:
            assert first in str(exc)
        else:
            raise AssertionError("duplicate order request should be rejected")
    finally:
        service.close()


def test_order_safety_schema_and_utc_timestamp(tmp_path: Path) -> None:
    service = TradingOrderService(tmp_path / "orders.db")
    try:
        columns = {
            row[1] for row in service.conn.execute("PRAGMA table_info(trade_order_requests)").fetchall()
        }
        assert "filled_quantity" in columns
        assert datetime.fromisoformat(service._now()).utcoffset() == timedelta(0)
        mode = service.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        service.close()


def test_dashboard_uses_forms_lazy_detail_views_and_current_width_api() -> None:
    root = Path(__file__).resolve().parents[1]
    kr = (root / "dashboard" / "trading_desk_app.py").read_text(encoding="utf-8")
    chart_first = (root / "dashboard" / "trading_desk_chart_first_app.py").read_text(encoding="utf-8")
    us = (root / "dashboard" / "us_trading_desk_app.py").read_text(encoding="utf-8")
    assert "with st.form(" in kr
    assert "with st.form(" in us
    assert "st.segmented_control(" in chart_first
    assert "use_container_width=True" not in kr + chart_first + us


def test_order_approval_claim_is_conditional() -> None:
    root = Path(__file__).resolve().parents[1]
    kr = (root / "trading" / "order_service.py").read_text(encoding="utf-8")
    us = (root / "trading" / "us_order_service.py").read_text(encoding="utf-8")
    assert "WHERE request_id=? AND status='PENDING_APPROVAL'" in kr
    assert "WHERE request_id=? AND status='PENDING_APPROVAL'" in us
    assert "'PARTIAL'" in kr
    assert "'PARTIAL'" in us


def test_dashboard_view_preference_persists(tmp_path: Path) -> None:
    service = TradingOrderService(tmp_path / "orders.db")
    try:
        assert service.dashboard_preference("kr_trading_view_mode", "기본 보기") == "기본 보기"
        service.set_dashboard_preference("kr_trading_view_mode", "상세 보기")
        assert service.dashboard_preference("kr_trading_view_mode", "기본 보기") == "상세 보기"
    finally:
        service.close()


def test_approved_dashboard_design_features_are_present() -> None:
    root = Path(__file__).resolve().parents[1]
    ui = (root / "dashboard" / "trading_desk_ui.py").read_text(encoding="utf-8")
    kr = (root / "dashboard" / "trading_desk_chart_first_app.py").read_text(encoding="utf-8")
    us = (root / "dashboard" / "us_trading_desk_app.py").read_text(encoding="utf-8")
    assert "render_mobile_bottom_nav" in ui
    assert "render_order_timeline" in ui
    assert "기본 보기" in ui and "상세 보기" in ui
    assert "with st.container(border=True)" in kr
    assert "① 주문 입력 → ② 내용 확인 → ③ 승인 대기" in us


def test_visual_system_theme_and_chart_conventions() -> None:
    root = Path(__file__).resolve().parents[1]
    theme = (root / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    charts = (root / "dashboard" / "charts.py").read_text(encoding="utf-8")
    kr = (root / "dashboard" / "trading_desk_app.py").read_text(encoding="utf-8")
    assert 'primaryColor = "#1D4ED8"' in theme
    assert 'backgroundColor = "#F6F8FB"' in theme
    assert "Pretendard" in theme
    assert 'increasing_line_color="#DC2626"' in charts
    assert 'decreasing_line_color="#2563EB"' in charts
    assert "height: int = 520" in charts
    assert "max-width:1480px" in kr


def test_workflow_navigation_targets_real_purpose_built_pages() -> None:
    root = Path(__file__).resolve().parents[1]
    navigation = (root / "dashboard_app.py").read_text(encoding="utf-8")
    assert 'pages/15_Validation_Report.py' in navigation
    assert 'pages/16_KR_Validation_History.py' in navigation
    assert 'pages/17_US_Validation_History.py' in navigation
    assert 'MOBILE_PAGES if mobile else PAGES' in navigation
    assert 'position="top" if mobile else "sidebar"' in navigation


def test_validation_report_and_history_pages_are_not_aliases() -> None:
    root = Path(__file__).resolve().parents[1]
    report = (root / "dashboard" / "validation_report_app.py").read_text(encoding="utf-8")
    history = (root / "dashboard" / "validation_history_app.py").read_text(encoding="utf-8")
    assert "종합 검증 리포트" in report
    assert "한국·미국 최신 완료 추천 실행" in report
    assert "검증 이력" in history
    assert "실행별 검증 현황" in history
