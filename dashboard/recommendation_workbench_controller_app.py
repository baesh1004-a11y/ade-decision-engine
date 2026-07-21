from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from dashboard import recommendation_workbench_v2_app as base
from maintenance.recommendation_runner import get_status
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, normalize_ticker
from recommendation.run_context import load_latest_context


def run() -> None:
    st.set_page_config(page_title="ADE 투자 워크벤치", page_icon="📊", layout="wide")
    base._style(st)

    title_col, market_col = st.columns([5, 1])
    with title_col:
        st.markdown(
            '<div class="page-title"><h1>투자 워크벤치</h1>'
            '<p>왼쪽 추천 목록에서 종목을 선택하면 분석·검증·주문 영역이 함께 변경됩니다.</p></div>',
            unsafe_allow_html=True,
        )
    with market_col:
        market = st.segmented_control(
            "시장", options=["kr", "us"], default="kr",
            format_func=lambda value: "🇰🇷 한국" if value == "kr" else "🇺🇸 미국",
            label_visibility="collapsed",
        )

    profile = get_market_profile(str(market or "kr"))
    if not profile.db_path.exists():
        st.error(f"{profile.db_path}가 없습니다.")
        return

    conn = sqlite3.connect(str(profile.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        context = load_latest_context(conn, profile.code, 50)
        base._render_generation_controls(st, profile, get_status(profile.code))
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

        base._render_context_banner(st, context)
        base._render_kpis(st, context, recommendations)

        left, center, right = st.columns([1.2, 3.2, 1.2], gap="medium")
        with left:
            base._step_title(st, 1, "추천 목록", "행을 클릭하면 전체 화면의 선택 종목이 변경됩니다.")
            _render_controller(st, recommendations, selected, profile.code)
        with center:
            base._step_title(st, 2, "분석 및 검증", "현재 차트와 과거 급등 직전 패턴을 비교합니다.")
            base._comparison_panel(
                st, selected, current, historical, pattern, payload,
                profile.code, profile.db_path, context.run_id, validation,
            )
        with right:
            base._step_title(st, 3, "주문", "선택 종목의 주문 화면으로 연결합니다.")
            base._order_panel(st, selected, profile.code, validation, context)
    finally:
        conn.close()


def _controller_selection(recommendations, market: str):
    key = f"workbench_selected_{market}"
    tickers = [str(row["ticker"]) for row in recommendations]
    if st.session_state.get(key) not in tickers:
        st.session_state[key] = tickers[0]
    return next(row for row in recommendations if str(row["ticker"]) == st.session_state[key])


def _render_controller(st, recommendations, selected, market: str) -> None:
    rows = []
    for row in recommendations[:20]:
        rows.append({
            "순위": int(row["rank_no"]),
            "종목": row["symbol"],
            "주봉": round(float(row["weekly_similarity"]), 1),
            "STO": round(float(row["sto_similarity"]), 1),
            "ticker": str(row["ticker"]),
        })
    frame = pd.DataFrame(rows)
    event = st.dataframe(
        frame[["순위", "종목", "주봉", "STO"]],
        use_container_width=True,
        hide_index=True,
        height=650,
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
    st.caption(f"현재 선택: {selected['symbol']}")
