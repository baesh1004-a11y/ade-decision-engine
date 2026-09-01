from __future__ import annotations

from dashboard.replay_target_chart import render_hts_comparison
from dashboard.replay_target_terminal import (
    SESSION_RESULT_KEY,
    render_replay_target_terminal,
)
from replay_target.integrated import IntegratedWatchConfig


def render_replay_watch_workspace() -> None:
    """Render Replay Watch metrics and always attempt the HTS-style comparison."""

    import streamlit as st

    render_replay_target_terminal()

    result = st.session_state.get(SESSION_RESULT_KEY)
    cfg = result.config if result is not None else IntegratedWatchConfig()
    resolved_anchor = (
        getattr(result, "resolved_reference_anchor_date", None)
        if result is not None
        else None
    )
    resolved_target = (
        getattr(result, "resolved_reference_target_date", None)
        if result is not None
        else None
    )

    st.markdown("### HTS형 경로 비교")
    st.caption(
        "왼쪽은 KODEX 코스닥150 현재 경로, 오른쪽은 AK홀딩스(당시 애경유화) 2011년 기준 경로입니다. "
        "가격 캔들·이동평균·STO 3계층을 같은 형식으로 나란히 봅니다. "
        "Target/Path 계산이 실패하거나 아직 준비되지 않아도 차트 데이터 로드는 별도로 시도합니다."
    )

    try:
        render_hts_comparison(
            st,
            cfg=cfg,
            resolved_reference_anchor_date=resolved_anchor,
            resolved_reference_target_date=resolved_target,
        )
    except Exception as exc:
        st.error(f"HTS형 비교차트 렌더링 실패: {exc}")
        st.caption("차트 오류가 점수 계산 화면 전체를 막지 않도록 분리했습니다.")
