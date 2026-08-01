from __future__ import annotations

import time

import streamlit as st

from dashboard.ade_ui_v1_app import *  # noqa: F401,F403
from dashboard.market_overview_service import (
    database_health,
    load_market_overview,
    load_sector_strength,
    market_health,
)

MARKET_REFRESH_SECONDS = 60


def _render_market_metrics() -> None:
    metrics, error = load_market_overview()
    ordered = ["kospi", "kosdaq", "sp500", "nasdaq", "usdkrw", "vix"]
    for col, key in zip(st.columns(6), ordered):
        item = metrics[key]
        if item.value is None:
            col.metric(item.label, item.status)
            if item.error:
                col.caption(item.error[:80])
            continue
        precision = 2
        value = f"{item.value:,.{precision}f}"
        delta = f"{item.change:+,.2f} · {item.change_rate:+.2f}%" if item.change is not None else None
        col.metric(item.label, value, delta)
        if item.updated_at:
            col.caption(f"{time.strftime('%H:%M:%S', time.localtime(item.updated_at))} · {item.source}")
    if error:
        st.warning(f"일부 시장 데이터 조회 실패: {error}")


def _render_market_overview() -> None:
    st.markdown("### 시장의 현재 정보")
    fragment = getattr(st, "fragment", None)
    if fragment is None:
        _render_market_metrics()
    else:
        @fragment(run_every=f"{MARKET_REFRESH_SECONDS}s")
        def _fragment_body() -> None:
            _render_market_metrics()
        _fragment_body()

    st.markdown("#### 주요 이벤트")
    st.info("경제 이벤트 공급원은 아직 연결되지 않았습니다. 데이터가 없는 상태를 정상 연결로 표시하지 않습니다.")

    st.markdown("#### 국내 섹터 강도")
    rows, sector_error = load_sector_strength(get_market_profile("kr").db_path)
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info(sector_error or "섹터 강도 데이터가 없습니다.")

    with st.expander("데이터 연결 진단"):
        metrics, market_error = load_market_overview()
        market_state = market_health(metrics, market_error)
        db_state = database_health(get_market_profile("kr").db_path)
        ws_state = shared_market_client().health_snapshot()
        st.dataframe(
            [
                {
                    "데이터 소스": "Yahoo Finance",
                    "상태": market_state.get("status"),
                    "최근 성공": time.strftime("%H:%M:%S", time.localtime(float(market_state["checked_at"]))) if market_state.get("checked_at") else "-",
                    "상세": market_state.get("detail"),
                },
                {
                    "데이터 소스": "SQLite",
                    "상태": db_state.get("status"),
                    "최근 성공": time.strftime("%H:%M:%S", time.localtime(float(db_state["checked_at"]))) if db_state.get("checked_at") else "-",
                    "상세": db_state.get("detail"),
                },
                {
                    "데이터 소스": "KIS WebSocket",
                    "상태": "정상" if ws_state.get("connected") and ws_state.get("latest_received_at") else ("연결·수신대기" if ws_state.get("connected") else "대기"),
                    "최근 성공": time.strftime("%H:%M:%S", time.localtime(float(ws_state["latest_received_at"]))) if ws_state.get("latest_received_at") else "-",
                    "상세": ws_state.get("last_error") or f"구독 {ws_state.get('subscription_count', 0)}개",
                },
            ],
            hide_index=True,
            use_container_width=True,
        )


def _render_status_bar() -> None:
    metrics, market_error = load_market_overview()
    market_state = market_health(metrics, market_error)
    db_state = database_health(get_market_profile("kr").db_path)
    ws_state = shared_market_client().health_snapshot()

    if kis_paper_enabled():
        kis_text, kis_class = "KIS 모의투자 설정", "ade-ok"
    elif kis_configured():
        kis_text, kis_class = "KIS 설정 확인 필요", ""
    else:
        kis_text, kis_class = "KIS 미설정", ""

    db_text = "DB 정상" if db_state.get("status") == "정상" else "DB 오류"
    db_class = "ade-ok" if db_state.get("status") == "정상" else ""
    yahoo_text = "Yahoo 정상" if market_state.get("status") == "정상" else "Yahoo 오류"
    yahoo_class = "ade-ok" if market_state.get("status") == "정상" else ""

    latest_received_at = ws_state.get("latest_received_at")
    if ws_state.get("connected") and latest_received_at:
        age = time.time() - float(latest_received_at)
        ws_text = "실시간 정상" if age <= 3 else ("실시간 지연" if age <= 10 else "실시간 오래됨")
        ws_class = "ade-ok" if age <= 3 else ""
    elif ws_state.get("connected"):
        ws_text, ws_class = "실시간 연결·수신대기", ""
    else:
        ws_text, ws_class = "실시간 대기", ""

    st.markdown(
        f'<div class="ade-statusbar"><span>AI 상태 미측정</span><span class="{db_class}">{db_text}</span>'
        f'<span class="{kis_class}">{kis_text}</span><span class="{ws_class}">{ws_text}</span>'
        f'<span class="{yahoo_class}">{yahoo_text}</span><span>추천·Replay·STO 규칙 유지</span></div>',
        unsafe_allow_html=True,
    )


def run() -> None:
    st.set_page_config(page_title="ADE Decision Engine", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
    _apply_zero_base_theme()
    _init_state()
    _render_top_navigation()
    page = st.session_state.ade_primary_page
    if page == "상황종합판":
        _render_overview()
    elif page == "추천결과":
        _render_recommendations()
    elif page == "주문":
        _render_orders()
    else:
        _render_jp_radar()
    _render_status_bar()


if __name__ == "__main__":
    run()
