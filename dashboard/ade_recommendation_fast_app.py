from __future__ import annotations

import streamlit as st

from dashboard import ade_ui_v1_app as base_ui
from dashboard.ade_recommendation_page import render_recommendation_page


@st.cache_data(ttl=30, show_spinner=False)
def _load_recommendation_snapshot(market: str):
    return base_ui._load_recommendations(market)


def _open_recommendation_detail(ticker: str) -> None:
    st.session_state.ade_recommendation_detail = ticker
    st.session_state.ade_show_heavy_charts = False
    st.rerun()


def _open_recommendation_jp(ticker: str) -> None:
    st.session_state.ade_primary_page = "JP Radar"
    st.session_state.ade_jp_ticker = ticker
    st.rerun()


def _open_recommendation_order(market: str, ticker: str, symbol: str) -> None:
    try:
        base_ui._add_order_candidate(market, ticker, symbol)
    except base_ui.OrderCandidateStoreError as exc:
        st.error(str(exc))
        return
    st.session_state.ade_primary_page = "주문"
    st.session_state.ade_order_ticker = ticker
    base_ui._reset_order_confirmation()
    st.rerun()


def run() -> None:
    st.set_page_config(
        page_title="ADE Recommendation",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    base_ui._apply_zero_base_theme()
    base_ui._init_state()
    if not st.session_state.ade_ui_workspace_confirmed:
        base_ui._render_workspace_selector()
        return
    base_ui._apply_workspace_theme()
    base_ui._render_top_navigation()

    market = base_ui._market_selector("ade_reco_market")
    if st.session_state.ade_recommendation_detail:
        base_ui._render_recommendation_detail(market, st.session_state.ade_recommendation_detail)
        return

    recommendations, context = _load_recommendation_snapshot(market)
    render_recommendation_page(
        market=market,
        recommendations=recommendations,
        context=context,
        open_detail=_open_recommendation_detail,
        open_jp=_open_recommendation_jp,
        open_order=lambda ticker, symbol: _open_recommendation_order(market, ticker, symbol),
    )


if __name__ == "__main__":
    run()
