from __future__ import annotations

from dashboard import ade_ui_v1_app as base_app
from dashboard.overview_market_panel import render_market_overview_panel


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


def run() -> None:
    base_app._render_overview = _render_overview
    base_app._render_status_bar = _render_status_bar
    base_app.run()


if __name__ == "__main__":
    run()
