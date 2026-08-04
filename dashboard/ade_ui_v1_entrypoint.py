from __future__ import annotations

from dashboard import ade_ui_v1_app as base_app
from dashboard.overview_market_panel import render_market_overview_panel
from dashboard.standard_order_panel import (
    OrderContext,
    render_order_ticket,
    render_scheduled_order_tab,
    render_search_launcher,
)


def _render_overview() -> None:
    import streamlit as st

    current = st.session_state.get("ade_overview_tab", "시장")
    if current not in {"시장", "내 투자"}:
        current = "시장"
    tab = st.segmented_control(
        "상황종합판 하위 메뉴",
        options=["시장", "내 투자"],
        default=current,
        key="ade_overview_segment",
        label_visibility="collapsed",
    )
    st.session_state.ade_overview_tab = tab or "시장"
    if tab == "내 투자":
        base_app._render_portfolio_overview()
    else:
        render_market_overview_panel()


def _render_status_bar() -> None:
    import time
    import streamlit as st

    from broker.kis_websocket import shared_market_client
    from dashboard.kis_zero_base_bridge import kis_configured, kis_paper_enabled
    from dashboard.order_candidate_store import store_health
    from dashboard.ui_workspace import get_workspace

    workspace = get_workspace(st.session_state.ade_ui_workspace)
    if kis_paper_enabled():
        kis_text, kis_class = "KIS 모의투자 설정", "ade-ok"
    elif kis_configured():
        kis_text, kis_class = "KIS 설정 확인 필요", ""
    else:
        kis_text, kis_class = "KIS 미설정", ""

    health = shared_market_client().health_snapshot()
    latest_received_at = health.get("latest_received_at")
    if health.get("connected") and latest_received_at:
        age = time.time() - float(latest_received_at)
        ws_text = "실시간 정상" if age <= 3 else ("실시간 지연" if age <= 10 else "실시간 오래됨")
        ws_class = "ade-ok" if age <= 3 else ""
    elif health.get("connected"):
        ws_text, ws_class = "실시간 연결·수신대기", ""
    else:
        ws_text, ws_class = "실시간 미사용 · 주문 화면에서 종목 선택 시 연결", ""

    candidate_health = store_health()
    schema_version = candidate_health.get("schema_version")
    candidate_text = f"후보DB 정상 v{schema_version}" if candidate_health.get("status") == "정상" else "후보DB 오류"
    candidate_class = "ade-ok" if candidate_health.get("status") == "정상" else ""
    st.markdown(
        f'<div class="ade-statusbar"><span>{workspace.short_name}</span><span>AI 데이터 부분 연결</span><span class="ade-ok">DB 정상</span><span class="{kis_class}">{kis_text}</span><span class="{ws_class}">{ws_text}</span><span>Yahoo 참고용</span><span class="{candidate_class}">{candidate_text}</span><span>추천·Replay·STO 규칙 유지</span></div>',
        unsafe_allow_html=True,
    )


def _open_order(ticker: str, symbol: str) -> None:
    import streamlit as st

    st.session_state.ade_order_ticker = ticker
    st.session_state.ade_order_symbol = symbol
    base_app._reset_order_confirmation()
    st.rerun()


def _save_candidate(market: str, ticker: str, symbol: str) -> None:
    import streamlit as st

    try:
        base_app._add_order_candidate(market, ticker, symbol)
        st.success(f"{symbol}을 주문후보에 저장했습니다.")
    except Exception as exc:
        st.error(str(exc))


def _submit_order(ticker: str, side: str, quantity: int, order_type: str, limit_price: float | None) -> tuple[bool, str]:
    try:
        result = base_app.submit_paper_order(
            ticker=ticker,
            side="BUY" if side == "매수" else "SELL",
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )
        if result.accepted:
            base_app.refresh_order_views()
            return True, f"접수 완료 · 주문번호 {result.order_id or '-'}"
        return False, "주문이 거절되었습니다."
    except Exception as exc:
        base_app.LOGGER.exception("Standard order submit failed ticker=%s", ticker)
        return False, f"주문 전송 실패: {exc}"


def _render_standard_order_ticket(market: str, ticker: str) -> None:
    import streamlit as st

    if st.button("← 주문목록으로 돌아가기", key="standard_order_back"):
        st.session_state.ade_order_ticker = None
        st.rerun()

    account, positions, account_error = base_app._cached_kis_snapshot() if market == "kr" else (None, [], None)
    quote, quote_error = base_app.load_kis_quote(ticker) if market == "kr" else (None, None)
    holding = next((row for row in positions if str(row.get("ticker")) == str(ticker)), None)
    name = str((holding or {}).get("name") or st.session_state.get("ade_order_symbol") or ticker)
    current_price = float((quote or {}).get("price") or (holding or {}).get("current_price") or 0)
    change_rate = float((quote or {}).get("change_rate") or 0)
    cash = float((account or {}).get("cash") or 0)
    orderable, orderable_error = base_app.load_orderable(ticker, current_price, "LIMIT") if market == "kr" else (None, None)
    orderable_quantity = int((orderable or {}).get("orderable_quantity") or 0)
    holding_quantity = int((holding or {}).get("quantity") or 0)

    context = OrderContext(
        market=market,
        ticker=ticker,
        name=name,
        current_price=current_price,
        change_rate=change_rate,
        cash=cash,
        holding_quantity=holding_quantity,
        orderable_quantity=orderable_quantity,
    )
    tabs = st.tabs(["일반주문", "예약주문"])
    with tabs[0]:
        render_order_ticket(context=context, submit_callback=_submit_order)
        details = [message for message in [account_error, quote_error, orderable_error] if message]
        if details:
            st.caption(" · ".join(details))
    with tabs[1]:
        render_scheduled_order_tab(
            market=market,
            ticker=ticker,
            name=name,
            current_price=current_price,
        )


def _render_orders() -> None:
    import streamlit as st

    base_app._render_order_flash()
    previous_market = st.session_state.ade_market
    market = base_app._market_selector("ade_order_market")
    if previous_market != market:
        base_app._release_live_lease()
        st.session_state.ade_order_ticker = None
        base_app._reset_order_confirmation()
        base_app._clear_live_session_state()
    st.session_state.ade_market = market

    if st.session_state.ade_order_ticker:
        _render_standard_order_ticket(market, str(st.session_state.ade_order_ticker))
        return

    st.markdown("### 주문")
    st.caption("종목 검색 → 주문 방향 → 주문 방식 → 수량 → 최종 확인 순서로 진행합니다.")
    render_search_launcher(
        market=market,
        search_func=base_app._search_order_symbols,
        on_open=_open_order,
        on_add_candidate=lambda ticker, symbol: _save_candidate(market, ticker, symbol),
    )

    tabs = st.tabs(["주문후보", "보유종목", "미체결", "당일 체결", "예약주문"])
    with tabs[0]:
        base_app._render_candidate_controls(market)
    with tabs[1]:
        account, positions, error = base_app._cached_kis_snapshot() if market == "kr" else (None, [], None)
        if not positions:
            st.info("보유종목이 없습니다.")
        for row in positions:
            if st.button(
                f"{row.get('name') or row.get('ticker')} · {row.get('ticker')} · {int(row.get('quantity') or 0)}주",
                key=f"standard_holding_{row.get('ticker')}",
                use_container_width=True,
            ):
                _open_order(str(row.get("ticker")), str(row.get("name") or row.get("ticker")))
        if account:
            st.caption(f"KIS 주문가능 현금 ₩{float(account.get('cash') or 0):,.0f}")
        if error:
            st.caption(error)
    with tabs[2]:
        base_app._render_pending_orders()
    with tabs[3]:
        base_app._render_daily_orders()
    with tabs[4]:
        render_scheduled_order_tab(market=market)


def run() -> None:
    base_app._render_overview = _render_overview
    base_app._render_status_bar = _render_status_bar
    base_app._render_orders = _render_orders
    base_app.run()


if __name__ == "__main__":
    run()
