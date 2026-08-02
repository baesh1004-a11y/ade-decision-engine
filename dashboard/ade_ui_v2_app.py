from __future__ import annotations

import time

import streamlit as st

from dashboard import ade_ui_v1_app as base_ui
from dashboard.ade_ui_v1_app import *  # noqa: F401,F403
from dashboard.ade_recommendation_page import render_recommendation_page
from dashboard.economic_calendar_service import load_economic_calendar
from dashboard.kis_zero_base_bridge import load_kis_index
from dashboard.market_overview_service import (
    database_health,
    load_market_overview,
    load_sector_strength,
    market_health,
)
from dashboard.news_disclosure_service import load_market_news, news_diagnostics

MARKET_REFRESH_SECONDS = 60
_KIS_INDEX_CODES = {"kospi": "0001", "kosdaq": "1001"}


@st.cache_data(ttl=60, show_spinner=False)
def _cached_market_overview():
    return load_market_overview()


@st.cache_data(ttl=600, show_spinner=False)
def _cached_economic_calendar(days_ahead: int = 90):
    return load_economic_calendar(days_ahead=days_ahead)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_sector_strength(db_path: str, limit: int = 10):
    return load_sector_strength(db_path, limit=limit)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_market_news(limit: int = 10):
    return load_market_news(limit=limit)


def _format_age(updated_at: float | None) -> str:
    if not updated_at:
        return "기준시각 없음"
    age = max(0, int(time.time() - float(updated_at)))
    if age < 60:
        return f"{age}초 전"
    if age < 3600:
        return f"{age // 60}분 전"
    return f"{age // 3600}시간 전"


def _render_market_metrics() -> None:
    metrics, error = _cached_market_overview()
    ordered = ["kospi", "kosdaq", "sp500", "nasdaq", "usdkrw", "vix"]
    kis_errors: list[str] = []

    for col, key in zip(st.columns(6), ordered):
        item = metrics[key]
        if key in _KIS_INDEX_CODES:
            kis_value, kis_error = load_kis_index(_KIS_INDEX_CODES[key])
            if kis_value is not None:
                value = float(kis_value.get("value") or 0)
                change = float(kis_value.get("change") or 0)
                change_rate = float(kis_value.get("change_rate") or 0)
                updated_at = float(kis_value.get("updated_at") or time.time())
                col.metric(item.label, f"{value:,.2f}", f"{change:+,.2f} · {change_rate:+.2f}%")
                col.caption(f"KIS · {item.market_state} · {_format_age(updated_at)}")
                continue
            if kis_error:
                kis_errors.append(f"{item.label}: {kis_error}")

        if item.value is None:
            col.metric(item.label, item.status)
            detail = item.error or "값을 검증할 수 없습니다."
            source_note = "Yahoo fallback" if key in _KIS_INDEX_CODES else item.source
            col.caption(f"{source_note} · {item.market_state} · {detail[:55]}")
            continue
        value = f"{item.value:,.2f}"
        delta = f"{item.change:+,.2f} · {item.change_rate:+.2f}%" if item.change is not None else None
        col.metric(item.label, value, delta)
        verified_text = "검증됨" if item.verified else "검증 필요"
        source_note = "Yahoo fallback" if key in _KIS_INDEX_CODES else item.source
        col.caption(
            f"{source_note} · {item.market_state} · {item.status} · {verified_text} · "
            f"{time.strftime('%m-%d %H:%M', time.localtime(item.updated_at)) if item.updated_at else '-'} "
            f"({_format_age(item.updated_at)})"
        )

    warnings: list[str] = []
    if error:
        warnings.append(error)
    if kis_errors:
        warnings.append("KIS 국내지수 조회 실패로 Yahoo 값을 사용했습니다: " + " | ".join(kis_errors))
    if warnings:
        st.warning("\n\n".join(warnings))
    st.caption("KOSPI·KOSDAQ은 KIS 우선, 실패 시 Yahoo fallback입니다. 미국지수·환율·VIX는 Yahoo 참고값입니다.")


def _render_event_table(*, compact: bool = False) -> None:
    rows, warning = _cached_economic_calendar(90)
    if rows:
        visible = rows[:5] if compact else rows
        st.dataframe(visible, hide_index=True, use_container_width=True)
    else:
        st.info("향후 90일 내 표시할 일정이 없습니다.")
    if warning:
        st.caption(warning)


def _render_sector_strength() -> None:
    db_path = str(get_market_profile("kr").db_path)
    rows, sector_error = _cached_sector_strength(db_path, 10)
    if not rows:
        st.info(sector_error or "섹터 강도 데이터가 없습니다.")
        return

    normalized = []
    for row in rows:
        turnover = row.get("turnover")
        normalized.append(
            {
                "업종": row.get("sector"),
                "등락률(%)": row.get("change_rate"),
                "강도점수": row.get("relative_strength"),
                "상승비율": row.get("breadth"),
                "거래대금(억원)": round(float(turnover) / 100_000_000, 1) if turnover not in (None, "") else None,
                "기준일": row.get("as_of") or "-",
                "출처": row.get("source") or "-",
            }
        )
    st.dataframe(normalized, hide_index=True, use_container_width=True)
    leader = normalized[0]
    st.caption(
        f"현재 강도 상위 업종: {leader['업종']} · 등락률 {float(leader.get('등락률(%)') or 0):+.2f}% · "
        f"강도점수 {float(leader.get('강도점수') or 0):.1f}"
    )
    if sector_error:
        st.caption(f"참고: {sector_error}")


def _render_market_news() -> None:
    rows, warning = _cached_market_news(10)
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("표시할 최신 시장 뉴스가 없습니다.")
    if warning:
        st.caption(warning)


def _render_market_overview() -> None:
    st.markdown("### 시장의 현재 정보")
    _render_market_metrics()

    if st.button("주요 이벤트 불러오기", key="load_overview_events", use_container_width=True):
        st.session_state.ade_show_overview_events = True
    if st.session_state.get("ade_show_overview_events", False):
        st.markdown("#### 주요 이벤트")
        _render_event_table(compact=True)

    if st.button("국내 섹터 강도 불러오기", key="load_overview_sectors", use_container_width=True):
        st.session_state.ade_show_overview_sectors = True
    if st.session_state.get("ade_show_overview_sectors", False):
        st.markdown("#### 국내 섹터 강도")
        _render_sector_strength()

    if st.button("최신 시장 뉴스 불러오기", key="load_overview_news", use_container_width=True):
        st.session_state.ade_show_overview_news = True
    if st.session_state.get("ade_show_overview_news", False):
        st.markdown("#### 최신 시장 뉴스")
        _render_market_news()

    if st.button("데이터 연결 진단 실행", key="run_overview_diagnostics", use_container_width=True):
        metrics, market_error = _cached_market_overview()
        market_state = market_health(metrics, market_error)
        db_state = database_health(get_market_profile("kr").db_path)
        ws_state = shared_market_client().health_snapshot()
        kis_rows = []
        for key, code in _KIS_INDEX_CODES.items():
            value, kis_error = load_kis_index(code)
            kis_rows.append(
                {
                    "데이터 소스": f"KIS {metrics[key].label}",
                    "상태": "정상" if value else "오류",
                    "최근 기준시각": time.strftime("%m-%d %H:%M:%S", time.localtime(float(value["updated_at"]))) if value and value.get("updated_at") else "-",
                    "상세": f"{float(value.get('value') or 0):,.2f}" if value else (kis_error or "조회 실패"),
                }
            )
        event_rows, event_warning = _cached_economic_calendar(90)
        sector_rows, sector_warning = _cached_sector_strength(str(get_market_profile("kr").db_path), 10)
        news_rows, news_warning = _cached_market_news(10)
        news_state = news_diagnostics()
        st.dataframe(
            kis_rows
            + [
                {
                    "데이터 소스": "경제 캘린더 · 공식/규칙 결합",
                    "상태": "연결" if event_rows else "데이터 없음",
                    "최근 기준시각": time.strftime("%m-%d %H:%M:%S"),
                    "상세": f"향후 90일 {len(event_rows)}건" + (f" · {event_warning}" if event_warning else ""),
                },
                {
                    "데이터 소스": "국내 섹터 강도",
                    "상태": "정상" if sector_rows else "오류",
                    "최근 기준시각": time.strftime("%m-%d %H:%M:%S"),
                    "상세": f"상위 {len(sector_rows)}개 업종" + (f" · {sector_warning}" if sector_warning else ""),
                },
                {
                    "데이터 소스": "시장 뉴스 · Google News RSS",
                    "상태": "정상" if news_rows else "오류",
                    "최근 기준시각": time.strftime("%m-%d %H:%M:%S"),
                    "상세": f"최신 {len(news_rows)}건 · DART {'설정됨' if news_state.get('dart_configured') else '미설정'}" + (f" · {news_warning}" if news_warning else ""),
                },
                {
                    "데이터 소스": "Yahoo 시장지표 · fallback/참고용",
                    "상태": market_state.get("status"),
                    "최근 기준시각": time.strftime("%m-%d %H:%M:%S", time.localtime(float(market_state["checked_at"]))) if market_state.get("checked_at") else "-",
                    "상세": market_state.get("detail"),
                },
                {
                    "데이터 소스": "SQLite",
                    "상태": db_state.get("status"),
                    "최근 점검": time.strftime("%m-%d %H:%M:%S", time.localtime(float(db_state["checked_at"]))) if db_state.get("checked_at") else "-",
                    "상세": db_state.get("detail"),
                },
                {
                    "데이터 소스": "KIS WebSocket",
                    "상태": "정상" if ws_state.get("connected") and ws_state.get("latest_received_at") else ("연결·수신대기" if ws_state.get("connected") else "대기"),
                    "최근 수신": time.strftime("%m-%d %H:%M:%S", time.localtime(float(ws_state["latest_received_at"]))) if ws_state.get("latest_received_at") else "-",
                    "상세": ws_state.get("last_error") or f"구독 {ws_state.get('subscription_count', 0)}개",
                },
            ],
            hide_index=True,
            use_container_width=True,
        )


def _render_event_page() -> None:
    st.markdown("### 주요 이벤트")
    _render_event_table(compact=False)


def _render_overview_v2() -> None:
    tabs = st.segmented_control(
        "상황종합판 하위 메뉴",
        options=["시장", "이벤트", "내 투자"],
        default=st.session_state.ade_overview_tab,
        key="ade_overview_segment",
        label_visibility="collapsed",
    )
    st.session_state.ade_overview_tab = tabs or "시장"
    if tabs == "시장":
        _render_market_overview()
    elif tabs == "이벤트":
        _render_event_page()
    else:
        base_ui._render_portfolio_overview()


def _open_recommendation_detail(ticker: str) -> None:
    st.session_state.ade_recommendation_detail = ticker
    st.session_state.ade_show_heavy_charts = False
    st.rerun()


def _open_recommendation_jp(ticker: str) -> None:
    st.session_state.ade_primary_page = "JP Radar"
    st.session_state.ade_jp_ticker = ticker
    st.rerun()


def _open_recommendation_order(market: str, ticker: str, symbol: str) -> None:
    try:
        base_ui._add_order_candidate(market, ticker, symbol)
    except base_ui.OrderCandidateStoreError as exc:
        st.error(str(exc))
        return
    st.session_state.ade_primary_page = "주문"
    st.session_state.ade_order_ticker = ticker
    base_ui._reset_order_confirmation()
    st.rerun()


@st.cache_data(ttl=20, show_spinner=False)
def _load_recommendation_snapshot(market: str):
    return base_ui._load_recommendations(market)


def _render_recommendations_v2() -> None:
    market = base_ui._market_selector("ade_reco_market")
    if st.session_state.ade_recommendation_detail:
        base_ui._render_recommendation_detail(market, st.session_state.ade_recommendation_detail)
        return
    recommendations, context = _load_recommendation_snapshot(market)
    render_recommendation_page(
        market=market,
        recommendations=recommendations,
        context=context,
        open_detail=_open_recommendation_detail,
        open_jp=_open_recommendation_jp,
        open_order=lambda ticker, symbol: _open_recommendation_order(market, ticker, symbol),
    )


def _render_status_bar(*, lightweight: bool = False) -> None:
    db_state = database_health(get_market_profile("kr").db_path)

    if kis_paper_enabled():
        kis_text, kis_class = "KIS 모의투자 설정", "ade-ok"
    elif kis_configured():
        kis_text, kis_class = "KIS 설정 확인 필요", ""
    else:
        kis_text, kis_class = "KIS 미설정", ""

    db_text = "DB 정상" if db_state.get("status") == "정상" else "DB 오류"
    db_class = "ade-ok" if db_state.get("status") == "정상" else ""

    if lightweight:
        st.markdown(
            f'<div class="ade-statusbar"><span>AI 상태 미측정</span><span class="{db_class}">{db_text}</span>'
            f'<span class="{kis_class}">{kis_text}</span><span>실시간 상태는 주문 화면에서 확인</span>'
            f'<span>시장지표는 상황종합판에서 확인</span><span>추천·Replay·STO 규칙 유지</span></div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div class="ade-statusbar"><span>AI 상태 미측정</span><span class="{db_class}">{db_text}</span>'
        f'<span class="{kis_class}">{kis_text}</span><span>외부 시장 조회는 현재 화면에서만 실행</span>'
        f'<span>실시간 상태는 주문 화면에서 확인</span><span>추천·Replay·STO 규칙 유지</span></div>',
        unsafe_allow_html=True,
    )


def run() -> None:
    st.set_page_config(page_title="ADE Decision Engine", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
    base_ui._apply_zero_base_theme()
    base_ui._init_state()
    if not st.session_state.ade_ui_workspace_confirmed:
        base_ui._render_workspace_selector()
        return
    base_ui._apply_workspace_theme()
    base_ui._render_top_navigation()
    page = st.session_state.ade_primary_page
    if page == "상황종합판":
        base_ui._release_live_lease()
        _render_overview_v2()
    elif page == "추천결과":
        base_ui._release_live_lease()
        _render_recommendations_v2()
    elif page == "주문":
        base_ui._render_orders()
    else:
        base_ui._release_live_lease()
        base_ui._render_jp_radar()
    _render_status_bar(lightweight=page == "추천결과")


if __name__ == "__main__":
    run()
