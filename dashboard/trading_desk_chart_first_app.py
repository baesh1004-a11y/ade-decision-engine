from __future__ import annotations

import os

from dashboard.trading_desk_app import (
    _render_ai_confidence_card,
    _render_analysis_actions,
    _render_execution_and_history,
    _render_live_chart,
    _render_order_form,
    _render_pending_approval,
    _render_selected_summary,
    _render_status_header,
    _style,
    _watch_label,
)
from markets.symbol_display import display_symbol, normalize_ticker
from trading.order_service import TradingOrderService


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 한국 주문관리", page_icon="💳", layout="wide")

    env = os.getenv("KIS_ENV", "paper").lower()
    live_enabled = os.getenv("KIS_LIVE_ORDER_ENABLED", "NO").upper() == "YES"
    service = TradingOrderService(db_path)

    try:
        recommendations = service.latest_recommendations(50)
        requests = service.pending_requests(100)
        current_run_id = str(recommendations[0]["run_id"]) if recommendations else ""
        pending_count = sum(
            1
            for row in requests
            if row["status"] == "PENDING_APPROVAL"
            and (not current_run_id or str(row.get("source_run_id") or "") == current_run_id)
        )

        _style(st)
        _render_status_header(st, env, live_enabled, len(recommendations), pending_count)
        st.markdown("### 1. 추천 Watch List")

        if not recommendations:
            st.warning("최신 완료 추천 결과가 없습니다. 먼저 통합 추천 워크벤치에서 추천을 생성하세요.")
            _render_pending_approval(st, service, recommendations)
            _render_execution_and_history(st, service)
            return

        run_id = str(recommendations[0]["run_id"])
        run_finished = str(recommendations[0].get("run_finished_at") or "-")
        st.caption(
            f"추천 완료: {run_finished} · "
            "왼쪽 목록에서 종목을 선택하면 오른쪽 차트와 판단 패널이 함께 바뀝니다."
        )

        labels = [_watch_label(row) for row in recommendations]
        selected_from_workbench = normalize_ticker(st.session_state.get("workbench_selected_kr") or "", "kr")
        default_index = next(
            (
                i
                for i, row in enumerate(recommendations)
                if normalize_ticker(row["ticker"], "kr") == selected_from_workbench
            ),
            0,
        )

        watch_column, detail_column = st.columns([1, 3], gap="large")
        with watch_column:
            st.markdown("#### 추천 종목")
            index = st.radio(
                "추천 종목 선택",
                range(len(recommendations)),
                index=default_index,
                format_func=lambda i: labels[i],
                key="trading_order_selected_kr_chart_first",
                label_visibility="collapsed",
            )
            st.caption("● 매수 검토  ● 관찰  ● 보류  ● 제외  ● 미검증")
            st.caption(f"총 {len(recommendations)}개 추천 종목")

        selected = recommendations[index]
        selected_code = normalize_ticker(selected["ticker"], "kr")
        selected_label = display_symbol(selected.get("name"), selected_code, "kr")
        st.session_state["workbench_selected_kr"] = selected_code

        with detail_column:
            _render_selected_summary(st, selected, selected_label)
            _render_live_chart(st, db_path, selected_code, selected_label)

            ai_tab, radar_tab, validation_tab, order_tab = st.tabs(
                ["AI 신뢰도", "JP Radar", "추천 검증", "주문"]
            )
            with ai_tab:
                _render_ai_confidence_card(st, selected, selected_code)
            with radar_tab:
                _render_analysis_actions(st, selected, selected_code)
            with validation_tab:
                st.session_state[f"validation_open_{selected_code}"] = True
                _render_analysis_actions(st, selected, selected_code)
            with order_tab:
                _render_order_form(st, service, selected, selected_code, selected_label, run_id)

        st.divider()
        _render_pending_approval(st, service, recommendations)
        _render_execution_and_history(st, service)
    finally:
        service.close()
