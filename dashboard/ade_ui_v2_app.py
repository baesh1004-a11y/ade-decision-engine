from __future__ import annotations

import time

import streamlit as st

from dashboard import ade_ui_v1_app as base_ui
from dashboard.ade_ui_v1_app import *  # noqa: F401,F403
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
    metrics, error = load_market_overview()
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
    rows, warning = load_economic_calendar(days_ahead=90)
    if rows:
        visible = rows[:5] if compact else rows
        st.dataframe(visible, hide_index=True, use_container_width=True)
    else:
        st.info("향후 90일 내 표시할 일정이 없습니다.")
    if warning:
        st.caption(warning)


def _render_sector_strength() -> None:
    rows, sector_error = load_sector_strength(get_market_profile("kr").db_path, limit=10)
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
    rows, warning = load_market_news(limit=10)
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("표시할 최신 시장 뉴스가 없습니다.")
    if warning:
        st.caption(warning)


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
    _render_event_table(compact=True)

    st.markdown("#### 국내 섹터 강도")
    _render_sector_strength()

    st.markdown("#### 최신 시장 뉴스")
    _render_market_news()

    with st.expander("데이터 연결 진단"):
        metrics, market_error = load_market_overview()
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
        event_rows, event_warning = load_economic_calendar(days_ahead=90)
        sector_rows, sector_warning = load_sector_strength(get_market_profile("kr").db_path, limit=10)
        news_rows, news_warning = load_market_news(limit=10)
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
    if market_state.get("status") == "정상":
        market_text, market_class = "시장지표 검증됨", "ade-ok"
    elif market_state.get("status") == "주의":
        market_text, market_class = "시장지표 검증 필요", ""
    else:
        market_text, market_class = "시장지표 오류", ""

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
        f'<span class="{market_class}">{market_text}</span><span>추천·Replay·STO 규칙 유지</span></div>',
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
        base_ui._render_recommendations()
    elif page == "주문":
        base_ui._render_orders()
    else:
        base_ui._release_live_lease()
        base_ui._render_jp_radar()
    _render_status_bar()


if __name__ == "__main__":
    run()
