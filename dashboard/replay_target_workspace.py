from __future__ import annotations

from dashboard.replay_target_chart import render_hts_comparison
from dashboard.replay_target_terminal import (
    SESSION_RESULT_KEY,
    render_replay_target_terminal,
)


def render_replay_watch_workspace() -> None:
    """Render the Replay Watch metrics and the HTS-style visual comparison."""

    import streamlit as st

    render_replay_target_terminal()

    result = st.session_state.get(SESSION_RESULT_KEY)
    if result is None:
        return

    st.markdown("### HTS형 경로 비교")
    st.caption(
        "왼쪽은 KODEX 코스닥150 현재 경로, 오른쪽은 AK홀딩스(당시 애경유화) 2011년 기준 경로입니다. "
        "가격 캔들·이동평균·STO 3계층을 같은 형식으로 나란히 봅니다."
    )
    render_hts_comparison(
        st,
        cfg=result.config,
        resolved_reference_anchor_date=getattr(result, "resolved_reference_anchor_date", None),
        resolved_reference_target_date=getattr(result, "resolved_reference_target_date", None),
    )
