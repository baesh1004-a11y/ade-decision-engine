from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from dashboard import recommendation_workbench_v2_app as base
from dashboard.daily_center_app import _initialize_widget_state, _persist_widget_state
from maintenance.recommendation_runner import get_status, start_job
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
        runtime = get_status(profile.code)
        _render_shared_generation_controls(profile, runtime, context)

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


def _render_shared_generation_controls(profile, runtime, context) -> None:
    """Use exactly the same settings, runner, runtime file and result DB as the market recommendation page."""
    fallback = context.parameters if context is not None and hasattr(context, "parameters") else None
    _initialize_widget_state(st, profile.code, fallback)

    years_key = f"{profile.code}_replay_years"
    pool_key = f"{profile.code}_weekly_pool"
    weekly_key = f"{profile.code}_weekly"
    sto_key = f"{profile.code}_sto"
    top_key = f"{profile.code}_top_n"

    with st.expander("추천 생성 설정 · 한국/미국 추천 메뉴와 공용", expanded=False):
        st.caption(
            "이 영역과 시장별 추천 메뉴는 동일한 설정 파일, 동일한 실행 작업, 동일한 DB 결과를 사용합니다. "
            "한 화면에서 시작한 작업은 다른 화면에서도 같은 상태로 표시됩니다."
        )
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.number_input("과거 패턴 기간(년)", 1, 10, step=1, key=years_key, on_change=_persist_widget_state, args=(st, profile.code))
        c2.number_input("비교할 과거 패턴 수", 10, 1000, step=10, key=pool_key, on_change=_persist_widget_state, args=(st, profile.code))
        c3.number_input("최소 주봉 유사도", 0.0, 100.0, step=1.0, key=weekly_key, on_change=_persist_widget_state, args=(st, profile.code))
        c4.number_input("STO 통과 기준", 0.0, 100.0, step=1.0, key=sto_key, on_change=_persist_widget_state, args=(st, profile.code))
        c5.number_input("저장할 추천 종목 수", 1, 50, step=1, key=top_key, on_change=_persist_widget_state, args=(st, profile.code))

        running = bool(runtime.get("running"))
        b1, b2, b3 = st.columns([3, 1, 1])
        if b1.button("추천 생성 및 저장", type="primary", use_container_width=True, disabled=running, key=f"workbench_run_{profile.code}"):
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
            else:
                st.warning("같은 시장의 추천 작업이 이미 다른 화면에서 실행 중입니다.")

        if b2.button("상태·결과 새로고침", use_container_width=True, key=f"workbench_refresh_{profile.code}"):
            st.rerun()
        target = "pages/7_Daily_Center.py" if profile.code == "kr" else "pages/10_US_Daily_Center.py"
        b3.page_link(target, label=f"{profile.name} 추천 화면", use_container_width=True)

        current_runtime = get_status(profile.code)
        state = str(current_runtime.get("state") or "IDLE")
        if bool(current_runtime.get("running")):
            progress = float(current_runtime.get("overall_progress", current_runtime.get("progress", 0.0)) or 0.0)
            current = int(current_runtime.get("current") or current_runtime.get("processed_symbols") or 0)
            total = int(current_runtime.get("total") or current_runtime.get("total_symbols") or 0)
            st.success("시장별 추천 메뉴와 공유된 추천 작업이 실행 중입니다.")
            st.progress(progress, text=str(current_runtime.get("message") or "추천 계산 중"))
            st.caption(
                f"상태 {state} · 처리 {current:,}/{total:,} · "
                f"최근 처리 종목 {current_runtime.get('current_ticker') or '-'} · "
                f"run 결과는 완료 후 두 화면에 동시에 반영됩니다."
            )
        elif state == "COMPLETED":
            st.success(
                f"공유 추천 작업 완료 · 추천 {int(current_runtime.get('recommendation_count') or 0)}개 · "
                "새로고침하면 최신 완료 실행이 워크벤치에 반영됩니다."
            )
        elif state in {"FAILED", "STALE", "CANCELLED"}:
            st.warning(str(current_runtime.get("error_message") or current_runtime.get("message") or state))


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
