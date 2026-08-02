from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard.daily_center_app import _initialize_widget_state, _persist_widget_state
from maintenance.recommendation_runner import get_status, start_job


def _format_seconds(value: object) -> str:
    try:
        seconds = max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds < 60:
        return f"{seconds:.1f}초"
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes}분 {remainder}초"


def _clear_recommendation_cache() -> None:
    try:
        from dashboard import ade_ui_v1_app as base_ui

        loader = getattr(base_ui, "_load_recommendations", None)
        clear = getattr(loader, "clear", None)
        if callable(clear):
            clear()
    except Exception:
        pass

    try:
        from dashboard import ade_ui_v2_app as v2_ui

        loader = getattr(v2_ui, "_load_recommendation_snapshot", None)
        clear = getattr(loader, "clear", None)
        if callable(clear):
            clear()
    except Exception:
        pass


def render_recommendation_controls(profile: Any) -> None:
    request_key = f"ade_recommendation_request_id_{profile.code}"
    completed_key = f"ade_recommendation_completed_id_{profile.code}"

    runtime = get_status(profile.code)
    runtime_request_id = str(runtime.get("request_id") or "")
    tracked_request_id = str(st.session_state.get(request_key) or "")

    if not tracked_request_id and runtime_request_id and bool(runtime.get("running")):
        st.session_state[request_key] = runtime_request_id
        tracked_request_id = runtime_request_id

    belongs_to_current_request = not tracked_request_id or not runtime_request_id or tracked_request_id == runtime_request_id
    if tracked_request_id and runtime_request_id and tracked_request_id != runtime_request_id:
        runtime = {
            "state": "IDLE",
            "running": False,
            "stage": "IDLE",
            "stage_label": "대기",
            "progress": 0.0,
            "overall_progress": 0.0,
            "request_id": tracked_request_id,
        }
        runtime_request_id = tracked_request_id
        belongs_to_current_request = False

    running = bool(runtime.get("running")) and belongs_to_current_request
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
        candidate_years = int(st.session_state[years_key])
        weekly_pool_n = int(st.session_state[pool_key])
        min_weekly_similarity = float(st.session_state[weekly_key])
        min_sto_similarity = float(st.session_state[sto_key])
        top_n = int(st.session_state[top_key])

        _persist_widget_state(st, profile.code)
        print(
            "[ADE][RECOMMEND][UI] "
            f"market={profile.code} years={candidate_years} pattern_limit={weekly_pool_n} "
            f"weekly_min={min_weekly_similarity:.1f} sto_min={min_sto_similarity:.1f} top_n={top_n}",
            flush=True,
        )
        request_id = start_job(
            profile.code,
            profile.db_path,
            top_n=top_n,
            weekly_pool_n=weekly_pool_n,
            candidate_years=candidate_years,
            use_recent_replay=True,
            use_weekly_filter=True,
            min_weekly_similarity=min_weekly_similarity,
            use_sto_filter=True,
            min_sto_similarity=min_sto_similarity,
        )
        if request_id:
            st.session_state[request_key] = str(request_id)
            st.session_state.pop(completed_key, None)
            st.session_state.ade_primary_page = "추천결과"
            st.rerun()
        else:
            st.warning("같은 시장의 추천 작업이 이미 실행 중입니다.")

    if action_cols[1].button(
        "결과 새로고침",
        use_container_width=True,
        key=f"ade_refresh_recommendation_{profile.code}",
    ):
        _clear_recommendation_cache()
        st.session_state.ade_primary_page = "추천결과"
        st.session_state.ade_recommendation_detail = None
        st.rerun()

    with action_cols[2].expander("추천 실행 설정", expanded=False):
        st.number_input("과거 패턴 기간(년)", 1, 10, step=1, key=years_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("비교할 과거 패턴 수", 10, 1000, step=10, key=pool_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("최소 주봉 유사도", 0.0, 100.0, step=1.0, key=weekly_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("STO 통과 기준", 0.0, 100.0, step=1.0, key=sto_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("저장할 추천 종목 수", 1, 50, step=1, key=top_key, on_change=_persist_widget_state, args=(st, profile.code))

    stage_label = str(runtime.get("stage_label") or runtime.get("stage") or state)
    current = int(runtime.get("current") or runtime.get("processed_symbols") or 0)
    total = int(runtime.get("total") or runtime.get("total_symbols") or 0)
    current_ticker = str(runtime.get("current_ticker") or "-")
    matched = int(runtime.get("matched_symbols") or 0)
    elapsed = _format_seconds(runtime.get("elapsed_seconds"))
    heartbeat_age = runtime.get("heartbeat_age_seconds")
    heartbeat_text = _format_seconds(heartbeat_age) if heartbeat_age is not None else "확인 불가"
    visible_request_id = str(runtime.get("request_id") or tracked_request_id or "-")

    if running:
        progress = float(runtime.get("overall_progress", runtime.get("progress", 0.0)) or 0.0)
        message = str(runtime.get("message") or f"처리 {current:,}/{total:,}")
        st.info("새 추천을 계산하고 있습니다. 기존 추천 결과는 완료 전까지 유지됩니다.")
        st.caption(f"현재 실행 ID: {visible_request_id}")
        st.progress(progress, text=message)
        details = st.columns(6)
        details[0].metric("현재 단계", stage_label)
        details[1].metric("처리 종목", f"{current:,}/{total:,}" if total else f"{current:,}")
        details[2].metric("현재 종목", current_ticker)
        details[3].metric("매칭 성공", f"{matched:,}개")
        details[4].metric("경과시간", elapsed)
        details[5].metric("Heartbeat", heartbeat_text)
    elif state == "COMPLETED" and belongs_to_current_request:
        completed_request_id = str(runtime.get("request_id") or "")
        if completed_request_id and st.session_state.get(completed_key) != completed_request_id:
            _clear_recommendation_cache()
            st.session_state[completed_key] = completed_request_id
        st.success(
            f"추천 실행 완료 · 추천 {int(runtime.get('recommendation_count') or 0)}건 · "
            f"소요 {elapsed}"
        )
        st.caption(
            f"요청 ID: {visible_request_id} · 결과 실행 ID: {runtime.get('run_id') or '-'}"
        )
    elif state in {"FAILED", "STALE", "CANCELLED"} and belongs_to_current_request:
        st.warning(str(runtime.get("error_message") or runtime.get("message") or state))
        st.caption(
            f"요청 ID: {visible_request_id} · 단계: {stage_label} · "
            f"경과시간: {elapsed} · Heartbeat: {heartbeat_text}"
        )
    elif tracked_request_id and not belongs_to_current_request:
        st.info(f"현재 화면은 요청 {tracked_request_id}의 상태를 기다리고 있습니다.")
