from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from dashboard.recommendation_detail_enhancements import (
    render_recommendation_detail_enhancements,
)


RenderHeavy = Callable[[], None]


def render_detail_with_lazy_heavy_sections(
    *,
    db_path: str,
    payload: dict[str, Any],
    selected: dict[str, Any],
    market: str,
    ticker: str,
    current: pd.DataFrame,
    current_label: str,
    render_heavy_sections: RenderHeavy,
) -> None:
    """Render lightweight recommendation details first, then optional heavy charts.

    This wrapper preserves the existing V1 heavy chart renderer while ensuring
    recommendation reasons, Replay Top N and Prediction are always available.
    """
    include_heavy = bool(st.session_state.get("ade_show_heavy_charts", False))
    render_recommendation_detail_enhancements(
        db_path=db_path,
        payload=payload,
        selected=selected,
        market=market,
        ticker=ticker,
        current=current,
        current_label=current_label,
        include_heavy=include_heavy,
    )

    if not include_heavy:
        if st.button(
            "상세 차트 불러오기",
            key=f"load_detail_charts_{market}_{ticker}",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.ade_show_heavy_charts = True
            st.rerun()
        return

    render_heavy_sections()
