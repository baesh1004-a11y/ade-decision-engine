from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard.daily_center_app import _initialize_widget_state, _persist_widget_state
from maintenance.recommendation_runner import get_status, start_job


def render_recommendation_controls(profile: Any) -> None:
    runtime = get_status(profile.code)
    running = bool(runtime.get("running"))
    state = str(runtime.get("state") or "IDLE")

    _initialize_widget_state(st, profile.code, None)
    years_key = f"{profile.code}_replay_years"
    pool_key = f"{profile.code}_weekly_pool"
    weekly_key = f"{profile.code}_weekly"
    sto_key = f"{profile.code}_sto"
    top_key = f"{profile.code}_top_n"

    action_cols = st.columns([1.4, 1, 3])
    if action_cols[0].button(
        "추천 실행",
        type="primary",
        use_container_width=True,
        disabled=running,
        key=f"ade_run_recommendation_{profile.code}",
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
        st.warning("같은 시장의 추천 작업이 이미 실행 중입니다.")

    if action_cols[1].button(
        "결과 새로고침",
        use_container_width=True,
        key=f"ade_refresh_recommendation_{profile.code}",
    ):
        st.rerun()

    with action_cols[2].expander("추천 실행 설정", expanded=False):
        st.number_input("과거 패턴 기간(년)", 1, 10, step=1, key=years_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("비교할 과거 패턴 수", 10, 1000, step=10, key=pool_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("최소 주봉 유사도", 0.0, 100.0, step=1.0, key=weekly_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("STO 통과 기준", 0.0, 100.0, step=1.0, key=sto_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("저장할 추천 종목 수", 1, 50, step=1, key=top_key, on_change=_persist_widget_state, args=(st, profile.code))

    if running:
        progress = float(runtime.get("overall_progress", runtime.get("progress", 0.0)) or 0.0)
        current = int(runtime.get("current") or runtime.get("processed_symbols") or 0)
        total = int(runtime.get("total") or runtime.get("total_symbols") or 0)
        message = str(runtime.get("message") or f"처리 {current:,}/{total:,}")
        st.info("새 추천을 계산하고 있습니다. 기존 추천 결과는 완료 전까지 유지됩니다.")
        st.progress(progress, text=message)
    elif state == "COMPLETED":
        st.success(f"최근 추천 실행 완료 · 추천 {int(runtime.get('recommendation_count') or 0)}건")
    elif state in {"FAILED", "STALE", "CANCELLED"}:
        st.warning(str(runtime.get("error_message") or runtime.get("message") or state))
