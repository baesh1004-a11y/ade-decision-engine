from __future__ import annotations

import streamlit as st

from dashboard.overview_market_panel import render_market_overview_panel


def render_overview(*, portfolio_renderer) -> None:
    current = st.session_state.get("ade_overview_tab", "시장")
    if current not in {"시장", "내 투자"}:
        current = "시장"
    selected = st.segmented_control(
        "상황종합판 하위 메뉴",
        options=["시장", "내 투자"],
        default=current,
        key="ade_overview_segment",
        label_visibility="collapsed",
    )
    st.session_state.ade_overview_tab = selected or "시장"
    if st.session_state.ade_overview_tab == "시장":
        render_market_overview_panel()
    else:
        portfolio_renderer()


def websocket_status_text(health: dict) -> tuple[str, str]:
    latest_received_at = health.get("latest_received_at")
    if health.get("connected") and latest_received_at:
        import time

        age = time.time() - float(latest_received_at)
        return (
            "실시간 정상" if age <= 3 else ("실시간 지연" if age <= 10 else "실시간 오래됨"),
            "ade-ok" if age <= 3 else "",
        )
    if health.get("connected"):
        return "실시간 연결·수신대기", ""
    return "실시간 미사용 · 주문 화면에서 종목 선택 시 연결", ""
