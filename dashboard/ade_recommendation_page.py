from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from dashboard.recommendation_controls import render_recommendation_controls
from markets.profiles import get_market_profile
from recommendation.run_context import latest_run


@st.cache_data(ttl=20, show_spinner=False)
def _load_latest_run_status(db_path: str, market: str) -> dict[str, Any] | None:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            return latest_run(conn, market)
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def _zero_result_summary(latest: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    diagnostics = dict(latest.get("diagnostics") or {})
    patterns_loaded = int(diagnostics.get("patterns_loaded") or 0)
    patterns_prepared = int(diagnostics.get("patterns_prepared") or 0)
    symbols_total = int(diagnostics.get("symbols_total") or 0)
    symbols_with_120d = int(diagnostics.get("symbols_with_120d") or 0)
    weekly_pass = int(diagnostics.get("weekly_pass_comparisons") or 0)
    sto_pass = int(diagnostics.get("sto_pass_comparisons") or 0)
    matched_symbols = int(diagnostics.get("symbols_with_matches") or 0)
    final_recommendations = int(diagnostics.get("final_recommendations") or 0)

    rows = [
        {"단계": "급등 패턴 조회", "통과": f"{patterns_loaded:,}개"},
        {"단계": "패턴 준비", "통과": f"{patterns_prepared:,}개"},
        {"단계": "분석 대상 종목", "통과": f"{symbols_total:,}개"},
        {"단계": "120일 데이터 확보", "통과": f"{symbols_with_120d:,}개"},
        {"단계": "주봉 기준 통과 비교", "통과": f"{weekly_pass:,}건"},
        {"단계": "STO 기준 통과 비교", "통과": f"{sto_pass:,}건"},
        {"단계": "매칭 성공 종목", "통과": f"{matched_symbols:,}개"},
        {"단계": "최종 추천", "통과": f"{final_recommendations:,}개"},
    ]

    if patterns_loaded == 0:
        reason = "최근 기간의 급등 직전 패턴이 없습니다. 패턴 DB 구축 상태를 확인해야 합니다."
    elif patterns_prepared == 0:
        reason = "조회된 패턴을 비교 가능한 형태로 준비하지 못했습니다."
    elif symbols_total == 0:
        reason = "분석할 활성 종목 목록이 없습니다."
    elif symbols_with_120d == 0:
        reason = "120거래일 데이터가 확보된 종목이 없습니다."
    elif weekly_pass == 0:
        reason = "모든 비교가 최소 주봉 유사도 기준에서 탈락했습니다."
    elif sto_pass == 0:
        reason = "주봉 기준 통과 후 모든 비교가 STO 기준에서 탈락했습니다."
    elif matched_symbols == 0:
        reason = "필터를 통과한 비교는 있었지만 최종 매칭 종목을 만들지 못했습니다."
    else:
        reason = "매칭 후보는 있었지만 최종 추천 목록이 0개입니다. 순위·저장 구간을 확인해야 합니다."
    return reason, rows


def _render_run_status(latest: dict[str, Any] | None, context: Any | None) -> None:
    if latest is None:
        return

    latest_run_id = str(latest.get("run_id") or "-")
    latest_status = str(latest.get("status") or "UNKNOWN")
    latest_count = int(latest.get("recommendation_count") or 0)
    latest_time = str(latest.get("finished_at") or latest.get("started_at") or "-")[:19]
    latest_error = str(latest.get("error_message") or "").strip()

    displayed_run_id = str(getattr(context, "run_id", "") or "")
    showing_previous = bool(displayed_run_id and displayed_run_id != latest_run_id)

    status_cols = st.columns(4)
    status_cols[0].metric("최근 실행 상태", latest_status)
    status_cols[1].metric("최근 실행 추천", f"{latest_count}개")
    status_cols[2].metric("최근 실행 시각", latest_time)
    status_cols[3].metric("표시 결과", "이전 성공 결과" if showing_previous else "최근 실행 결과")

    st.caption(f"최근 실행 ID: {latest_run_id}")
    if latest_error:
        st.warning(f"최근 실행 오류: {latest_error}")
    elif latest_status == "COMPLETED" and latest_count == 0:
        reason, rows = _zero_result_summary(latest)
        st.warning(f"최근 실행은 완료됐지만 추천 종목이 0개입니다. 원인 추정: {reason}")
        with st.expander("추천 0건 단계별 진단", expanded=False):
            st.dataframe(rows, hide_index=True, use_container_width=True)
    elif latest_status in {"FAILED", "CANCELLED", "STALE", "RUNNING"} and showing_previous:
        st.info("최근 실행에 표시할 추천 결과가 없어 이전 성공 결과를 유지하고 있습니다.")


def render_recommendation_page(
    *,
    market: str,
    recommendations: list[dict[str, Any]],
    context: Any | None,
    open_detail: Callable[[str], None],
    open_jp: Callable[[str], None],
    open_order: Callable[[str, str], None],
) -> None:
    profile = get_market_profile(market)
    st.markdown(f"### {'국내' if market == 'kr' else '미국'} 추천종목")
    render_recommendation_controls(profile)

    latest = _load_latest_run_status(str(profile.db_path), market)
    _render_run_status(latest, context)

    if context is not None:
        st.caption(
            f"현재 표시 결과 · 실행ID {context.run_id} · 생성 {str(context.finished_at or '-')[:19]} · "
            f"추천 {context.recommendation_count}개"
        )

    if not recommendations:
        st.info("저장된 추천 결과가 없습니다. 추천 실행 버튼으로 새 추천을 생성하세요.")
        return

    for row in recommendations:
        cols = st.columns([0.55, 3.2, 1.25, 1.05, 1.05])
        ticker = str(row.get("ticker") or "")
        symbol = str(row.get("symbol") or row.get("name") or ticker)
        cols[0].markdown(f"**#{int(row.get('rank_no', 0))}**")
        if cols[1].button(
            f"{symbol}\n\n{ticker}",
            key=f"detail_{market}_{ticker}",
            use_container_width=True,
        ):
            open_detail(ticker)

        score = float(row.get("final_similarity") or row.get("weekly_similarity") or 0)
        cols[2].metric("종합 유사도", f"{score:.1f}")
        if cols[3].button("JP Radar", key=f"jp_{market}_{ticker}", use_container_width=True):
            open_jp(ticker)
        if cols[4].button(
            "주문",
            key=f"order_{market}_{ticker}",
            type="primary",
            use_container_width=True,
        ):
            open_order(ticker, symbol)
        st.divider()
