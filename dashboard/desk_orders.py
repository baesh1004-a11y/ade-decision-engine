"""US candidates use the existing USD request and approval workflow."""

from __future__ import annotations

import streamlit as st

from dashboard.desk_data import DeskData
from dashboard.order_candidate_store import list_candidates
from markets.profiles import get_market_profile
from trading.us_order_service import USTradingOrderService


def render_us_orders() -> None:
    from dashboard.ade_ui_v1_entrypoint import _render_candidate_origin
    from dashboard.us_trading_desk_app import (
        _render_execution,
        _render_order_form,
        _render_pending,
    )

    profile = get_market_profile("us")
    service = USTradingOrderService(profile.db_path)
    try:
        candidates = list_candidates(str(st.session_state.ade_owner_id), "us")
        ticker = st.session_state.get("ade_order_ticker")
        selected = None
        if ticker:
            ticker = str(ticker)
            if st.button("← 주문목록으로 돌아가기", key="desk_us_back"):
                st.session_state.ade_order_ticker = None
                st.rerun()
            _render_candidate_origin("us", ticker)
            candidate = next((row for row in candidates if row["ticker"] == ticker), {})
            run_id = candidate.get("source_run_id")
            if run_id:
                context = DeskData(profile.db_path, "us").context(str(run_id))
                selected = (
                    next(
                        (
                            row
                            for row in context.recommendations
                            if row["ticker"] == ticker
                        ),
                        None,
                    )
                    if context
                    else None
                )
                if selected is None:
                    st.warning(
                        "주문 후보의 원래 추천을 찾을 수 없습니다. 추천 근거를 다시 선택하세요."
                    )
            else:
                selected = {
                    "ticker": ticker,
                    "name": candidate.get("symbol") or ticker,
                    "run_id": None,
                    "rank_no": None,
                }
            if selected is not None:
                st.subheader(f"{selected.get('name') or ticker} · {ticker}")
                st.caption("미국 주식 · USD 지정가 · 요청 저장 후 사용자 승인")
                _render_order_form(st, service, selected, ticker)
        else:
            st.subheader("미국 주문 후보")
            if not candidates:
                st.info("추천 화면에서 검토한 종목을 주문 후보로 보내세요.")
            for row in candidates:
                if st.button(
                    f"{row['symbol']} · {row['ticker']}",
                    key="desk_us_candidate_" + row["ticker"],
                    use_container_width=True,
                ):
                    st.session_state.ade_order_ticker = row["ticker"]
                    st.rerun()
        _render_pending(
            st, service, [selected] if selected and selected.get("run_id") else []
        )
        with st.expander("미국 체결·보유 관리"):
            _render_execution(st, service)
    finally:
        service.close()
