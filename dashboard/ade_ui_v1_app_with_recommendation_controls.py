from __future__ import annotations

from dashboard.ade_ui_v1_app import *  # noqa: F401,F403
from dashboard.ade_recommendation_page import render_recommendation_page


def _open_recommendation_detail(ticker: str) -> None:
    st.session_state.ade_recommendation_detail = ticker
    st.session_state.ade_show_heavy_charts = False
    st.rerun()


def _open_jp_radar(ticker: str) -> None:
    st.session_state.ade_primary_page = "JP Radar"
    st.session_state.ade_jp_ticker = ticker
    st.rerun()


def _open_order(market: str, ticker: str, symbol: str) -> None:
    try:
        _add_order_candidate(market, ticker, symbol)
    except OrderCandidateStoreError as exc:
        st.error(str(exc))
        return
    st.session_state.ade_primary_page = "주문"
    st.session_state.ade_order_ticker = ticker
    _reset_order_confirmation()
    st.rerun()


def _render_recommendations() -> None:
    market = _market_selector("ade_reco_market")
    if st.session_state.ade_recommendation_detail:
        _render_recommendation_detail(market, st.session_state.ade_recommendation_detail)
        return

    recommendations, context = _load_recommendations(market)
    render_recommendation_page(
        market=market,
        recommendations=recommendations,
        context=context,
        open_detail=_open_recommendation_detail,
        open_jp=_open_jp_radar,
        open_order=lambda ticker, symbol: _open_order(market, ticker, symbol),
    )


if __name__ == "__main__":
    run()
