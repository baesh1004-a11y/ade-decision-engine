from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from dashboard import recommendation_workbench_v2_app as base
from dashboard.daily_center_app import _initialize_widget_state, _persist_widget_state
from dashboard.design_system import StatusBadge, apply_design_system, page_header, section, step_header
from maintenance.recommendation_runner import get_status, start_job
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, normalize_ticker
from recommendation.run_context import load_latest_context


def _state_label(state: str) -> str:
    return {
        "IDLE": "대기",
        "STARTING": "시작 중",
        "RUNNING": "실행 중",
        "COMPLETED": "완료",
        "FAILED": "실패",
        "STALE": "연결 끊김",
        "CANCELLED": "취소됨",
        "CANCELLING": "취소 중",
    }.get(state, state or "대기")


def run() -> None:
    st.set_page_config(page_title="ADE 추천종목 분석", page_icon="📊", layout="wide")
    apply_design_system()

    market = st.segmented_control(
        "시장",
        options=["kr", "us"],
        default="kr",
        format_func=lambda value: "🇰🇷 국내" if value == "kr" else "🇺🇸 미국",
        label_visibility="collapsed",
    )
    profile = get_market_profile(str(market or "kr"))
    runtime = get_status(profile.code)
    state = str(runtime.get("state") or "IDLE")
    tone = "success" if state == "COMPLETED" else "warning" if state in {"STARTING", "RUNNING", "CANCELLING"} else "error" if state in {"FAILED", "STALE", "CANCELLED"} else "info"
    page_header(
        "추천종목 분석",
        "추천 종목을 선택하고 분석·검증·주문으로 연결합니다.",
        eyebrow="ADE · RECOMMENDATION WORKBENCH",
        badges=(StatusBadge(profile.name, "info"), StatusBadge(_state_label(state), tone)),
    )

    if not profile.db_path.exists():
        st.error(f"데이터베이스를 찾을 수 없습니다: {profile.db_path}")
        return

    conn = sqlite3.connect(str(profile.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        context = load_latest_context(conn, profile.code, 50)
        _render_generation_controls(profile, runtime, context)

        if context is None:
            st.info("저장된 추천 결과가 없습니다. 추천 생성 버튼을 먼저 실행하세요.")
            return

        name_map = build_name_map(conn, profile.code)
        recommendations = base._enrich_recommendations(context.recommendations, name_map, profile.code)
        selected = _controller_selection(recommendations, profile.code)
        ticker = normalize_ticker(selected["ticker"], profile.code)
        payload = base._safe_json(selected.get("payload_json"))
        validation = context.validations.get(ticker) or context.validations.get(str(selected["ticker"]))
        pattern = base._selected_pattern(conn, payload)
        current = base._current_bars(conn, profile.code, ticker, profile.price_source)
        historical = base._pattern_bars(conn, pattern)

        summary_cols = st.columns(3)
        summary_cols[0].metric("추천 결과", f"{len(recommendations)}건")
        summary_cols[1].metric("환경 조언", f"{len(context.validations)}건")
        summary_cols[2].metric("선택 종목", selected["symbol"])
        st.caption(
            f"실행 ID {context.run_id} · 최근 실행 {context.finished_at or '-'} · "
            f"실행 유형 {context.run_type or '-'} · 주문 {len(context.current_orders)}건"
        )

        step_header(1, "추천 목록", "검토할 종목을 선택합니다.")
        _render_controller(recommendations, selected, profile.code)

        step_header(2, "분석 및 검증", "차트와 검증 결과를 확인합니다.")
        base._comparison_panel(
            st,
            selected,
            current,
            historical,
            pattern,
            payload,
            profile.code,
            profile.db_path,
            context.run_id,
            validation,
        )

        step_header(3, "주문", "검토한 종목을 주문 화면으로 연결합니다.")
        base._order_panel(st, selected, profile.code, validation, context)
    finally:
        conn.close()


def _render_generation_controls(profile, runtime, context) -> None:
    fallback = context.parameters if context is not None and hasattr(context, "parameters") else None
    _initialize_widget_state(st, profile.code, fallback)

    years_key = f"{profile.code}_replay_years"
    pool_key = f"{profile.code}_weekly_pool"
    weekly_key = f"{profile.code}_weekly"
    sto_key = f"{profile.code}_sto"
    top_key = f"{profile.code}_top_n"

    section("추천 설정", "추천 생성 기준과 저장 수량을 설정합니다.")
    with st.expander("상세 설정", expanded=False):
        st.number_input("과거 패턴 기간(년)", 1, 10, step=1, key=years_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("비교할 과거 패턴 수", 10, 1000, step=10, key=pool_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("최소 주봉 유사도", 0.0, 100.0, step=1.0, key=weekly_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("STO 통과 기준", 0.0, 100.0, step=1.0, key=sto_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("저장할 추천 종목 수", 1, 50, step=1, key=top_key, on_change=_persist_widget_state, args=(st, profile.code))

        running = bool(runtime.get("running"))
        action_cols = st.columns(2)
        if action_cols[0].button(
            "추천 생성 및 저장",
            type="primary",
            use_container_width=True,
            disabled=running,
            key=f"workbench_run_{profile.code}",
        ):
            _persist_widget_state(st, profile.code)
            started = start_job(
                profile.code,
                profile.db_path,
                top_n=int(st.session_state[top_key]),
                weekly_pool_n=int(st.session_state[pool_key]),
                candidate_years=int(st.session_state[years_key]),
                use_recent_replay=True,
                use_weekly_filter=True,
                min_weekly_similarity=float(st.session_state[weekly_key]),
                use_sto_filter=True,
                min_sto_similarity=float(st.session_state[sto_key]),
            )
            if started:
                st.rerun()
            else:
                st.warning("같은 시장의 추천 작업이 이미 실행 중입니다.")

        if action_cols[1].button("다시 불러오기", use_container_width=True, key=f"workbench_refresh_{profile.code}"):
            st.rerun()

        current_runtime = get_status(profile.code)
        state = str(current_runtime.get("state") or "IDLE")
        if bool(current_runtime.get("running")):
            progress = float(current_runtime.get("overall_progress", current_runtime.get("progress", 0.0)) or 0.0)
            current = int(current_runtime.get("current") or current_runtime.get("processed_symbols") or 0)
            total = int(current_runtime.get("total") or current_runtime.get("total_symbols") or 0)
            st.info("추천 작업을 실행하고 있습니다.")
            st.progress(progress, text=str(current_runtime.get("message") or f"처리 {current:,}/{total:,}"))
        elif state == "COMPLETED":
            st.success(f"추천 완료 · {int(current_runtime.get('recommendation_count') or 0)}건")
        elif state in {"FAILED", "STALE", "CANCELLED"}:
            st.warning(str(current_runtime.get("error_message") or current_runtime.get("message") or _state_label(state)))


def _controller_selection(recommendations, market: str):
    key = f"workbench_selected_{market}"
    tickers = [str(row["ticker"]) for row in recommendations]
    if st.session_state.get(key) not in tickers:
        st.session_state[key] = tickers[0]
    return next(row for row in recommendations if str(row["ticker"]) == st.session_state[key])


def _render_controller(recommendations, selected, market: str) -> None:
    rows = []
    for row in recommendations[:20]:
        rows.append(
            {
                "순위": int(row["rank_no"]),
                "종목": row["symbol"],
                "주봉 유사도": round(float(row["weekly_similarity"]), 1),
                "STO 유사도": round(float(row["sto_similarity"]), 1),
                "ticker": str(row["ticker"]),
            }
        )
    frame = pd.DataFrame(rows)
    event = st.dataframe(
        frame[["순위", "종목", "주봉 유사도", "STO 유사도"]],
        use_container_width=True,
        hide_index=True,
        height=520,
        on_select="rerun",
        selection_mode="single-row",
        key=f"workbench_controller_{market}",
    )
    selected_rows = getattr(getattr(event, "selection", None), "rows", [])
    if selected_rows:
        ticker = frame.iloc[int(selected_rows[0])]["ticker"]
        if ticker != st.session_state.get(f"workbench_selected_{market}"):
            st.session_state[f"workbench_selected_{market}"] = ticker
            st.rerun()

    with st.expander("모바일 종목 선택", expanded=False):
        for row in recommendations[:12]:
            ticker = str(row["ticker"])
            is_selected = ticker == str(selected["ticker"])
            rank_no = int(row["rank_no"])
            weekly = float(row["weekly_similarity"])
            sto = float(row["sto_similarity"])
            label = f"{'✓ ' if is_selected else ''}#{rank_no} {row['symbol']} · 주봉 {weekly:.1f}% · STO {sto:.1f}%"
            if st.button(label, key=f"workbench_mobile_card_{market}_{ticker}", use_container_width=True):
                st.session_state[f"workbench_selected_{market}"] = ticker
                st.rerun()


if __name__ == "__main__":
    run()
