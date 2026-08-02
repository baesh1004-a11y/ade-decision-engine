from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from dashboard.recommendation_controls import render_recommendation_controls
from markets.profiles import get_market_profile


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

    if context is not None:
        st.caption(
            f"실행ID {context.run_id} · 생성 {str(context.finished_at or '-')[:19]} · "
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
