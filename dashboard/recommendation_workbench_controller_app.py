from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from dashboard import recommendation_workbench_v2_app as base
from dashboard.daily_center_app import _initialize_widget_state, _persist_widget_state
from dashboard.design_system import StatusBadge, apply_design_system, page_header, step_header
from maintenance.recommendation_runner import get_status, start_job
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, normalize_ticker
from recommendation.run_context import load_latest_context


def run() -> None:
    st.set_page_config(page_title="ADE 투자 워크벤치", page_icon="📊", layout="wide")
    apply_design_system()
    st.markdown(
        """
        <style>
        .wb-mobile-flow{display:none}
        @media(max-width:640px){
          .wb-header-row div[data-testid="stHorizontalBlock"]{
            display:block!important;
          }
          .wb-header-row div[data-testid="stColumn"]{
            min-width:0!important;width:100%!important;flex:none!important;
          }
          .wb-market-selector{margin:-2px 0 5px}
          .wb-market-selector [data-testid="stSegmentedControl"]{width:100%!important}
          .wb-market-selector [data-testid="stSegmentedControl"]>div{
            display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;
            width:100%!important;gap:3px!important;padding:2px!important;
            border:1px solid #d9e5ef!important;border-radius:8px!important;background:#edf3f8!important;
          }
          .wb-market-selector button{
            width:100%!important;min-height:28px!important;padding:0 5px!important;
            border-radius:6px!important;font-size:9px!important;font-weight:800!important;
          }
          .wb-desktop-flow{display:none!important}
          .wb-mobile-flow{display:block!important}
          .wb-mobile-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;margin:4px 0 6px}
          .wb-mobile-summary-item{display:flex;align-items:center;gap:5px;min-width:0;padding:6px;border:1px solid #d8e2ec;border-radius:8px;background:#fff}
          .wb-mobile-summary-icon{font-size:14px;line-height:1}
          .wb-mobile-summary-item span{display:block;font-size:7.5px;color:#64788d;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
          .wb-mobile-summary-item strong{display:block;font-size:11px;line-height:1.1;color:#102235}
          .wb-mobile-settings [data-testid="stExpander"]{margin:0 0 5px!important}
          .wb-mobile-settings [data-testid="stExpanderDetails"]{padding:5px 6px 6px!important}
          .wb-mobile-settings [data-testid="stCaptionContainer"]{display:none!important}
          .wb-settings-grid div[data-testid="stHorizontalBlock"]{
            display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:4px!important;
          }
          .wb-settings-grid div[data-testid="stColumn"]{min-width:0!important;width:auto!important;flex:none!important}
          .wb-settings-grid div[data-testid="stColumn"]:last-child{grid-column:1 / -1!important}
          .wb-settings-grid label{font-size:8.5px!important;line-height:1.1!important}
          .wb-settings-grid input{min-height:28px!important;font-size:10px!important}
          .wb-settings-actions div[data-testid="stHorizontalBlock"]{
            display:grid!important;grid-template-columns:1.35fr 1fr!important;gap:4px!important;
          }
          .wb-settings-actions div[data-testid="stColumn"]{min-width:0!important;width:auto!important;flex:none!important}
          .wb-settings-actions div[data-testid="stColumn"]:nth-child(3){display:none!important}
          .wb-settings-actions .stButton>button{min-height:30px!important;font-size:9.5px!important;border-radius:7px!important}
          .wb-mobile-runtime{margin-top:4px}
          .wb-mobile-runtime [data-testid="stAlert"]{margin:3px 0!important}
          .wb-mobile-flow>.ade-step{margin-top:5px!important}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="wb-header-row">', unsafe_allow_html=True)
    title_col, market_col = st.columns([5, 1])
    with title_col:
        page_header(
            "투자 워크벤치",
            "추천 종목 선택부터 분석, 환경 검증, 주문 연결까지 한 화면에서 처리합니다.",
            badges=[StatusBadge("AI DECISION WORKSPACE", "info")],
        )
    with market_col:
        st.markdown('<div class="wb-market-selector">', unsafe_allow_html=True)
        market = st.segmented_control(
            "시장", options=["kr", "us"], default="kr",
            format_func=lambda value: "🇰🇷 한국" if value == "kr" else "🇺🇸 미국",
            label_visibility="collapsed",
        )
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

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

        st.markdown(
            f"""
            <div class="wb-mobile-summary">
              <div class="wb-mobile-summary-item"><div class="wb-mobile-summary-icon">☆</div><div><span>추천 수</span><strong>{len(recommendations)}건</strong></div></div>
              <div class="wb-mobile-summary-item"><div class="wb-mobile-summary-icon">♢</div><div><span>검증 수</span><strong>{len(context.validations)}건</strong></div></div>
              <div class="wb-mobile-summary-item"><div class="wb-mobile-summary-icon">▣</div><div><span>선택 종목</span><strong>{selected['symbol']}</strong></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="wb-desktop-flow">', unsafe_allow_html=True)
        base._render_context_banner(st, context)
        base._render_kpis(st, context, recommendations)
        left, center, right = st.columns([1.2, 3.2, 1.2], gap="medium")
        with left:
            step_header(1, "추천 목록", "종목을 선택하면 분석과 주문 영역이 함께 변경됩니다.")
            _render_controller(st, recommendations, selected, profile.code)
        with center:
            step_header(2, "분석 및 검증", "현재 차트와 과거 급등 직전 패턴을 비교합니다.")
            base._comparison_panel(
                st, selected, current, historical, pattern, payload,
                profile.code, profile.db_path, context.run_id, validation,
            )
        with right:
            step_header(3, "주문", "선택 종목의 주문 화면으로 연결합니다.")
            base._order_panel(st, selected, profile.code, validation, context)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="wb-mobile-flow">', unsafe_allow_html=True)
        step_header(1, "추천·분석", "종목을 선택하고 차트와 검증 결과를 함께 확인합니다.")
        _render_controller(st, recommendations, selected, profile.code)
        base._comparison_panel(
            st, selected, current, historical, pattern, payload,
            profile.code, profile.db_path, context.run_id, validation,
        )
        step_header(2, "주문", "선택 종목의 주문 화면으로 연결합니다.")
        base._order_panel(st, selected, profile.code, validation, context)
        st.markdown('</div>', unsafe_allow_html=True)
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

    st.markdown('<div class="wb-mobile-settings">', unsafe_allow_html=True)
    with st.expander("추천 설정", expanded=False):
        st.caption(
            "이 영역과 시장별 추천 메뉴는 동일한 설정 파일, 동일한 실행 작업, 동일한 DB 결과를 사용합니다. "
            "한 화면에서 시작한 작업은 다른 화면에서도 같은 상태로 표시됩니다."
        )
        st.markdown('<div class="wb-settings-grid">', unsafe_allow_html=True)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.number_input("과거 패턴 기간(년)", 1, 10, step=1, key=years_key, on_change=_persist_widget_state, args=(st, profile.code))
        c2.number_input("비교할 과거 패턴 수", 10, 1000, step=10, key=pool_key, on_change=_persist_widget_state, args=(st, profile.code))
        c3.number_input("최소 주봉 유사도", 0.0, 100.0, step=1.0, key=weekly_key, on_change=_persist_widget_state, args=(st, profile.code))
        c4.number_input("STO 통과 기준", 0.0, 100.0, step=1.0, key=sto_key, on_change=_persist_widget_state, args=(st, profile.code))
        c5.number_input("저장할 추천 종목 수", 1, 50, step=1, key=top_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.markdown('</div>', unsafe_allow_html=True)

        running = bool(runtime.get("running"))
        st.markdown('<div class="wb-settings-actions">', unsafe_allow_html=True)
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

        if b2.button("새로고침", use_container_width=True, key=f"workbench_refresh_{profile.code}"):
            st.rerun()
        target = "pages/7_Daily_Center.py" if profile.code == "kr" else "pages/10_US_Daily_Center.py"
        b3.page_link(target, label=f"{profile.name} 추천 화면", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="wb-mobile-runtime">', unsafe_allow_html=True)
        current_runtime = get_status(profile.code)
        state = str(current_runtime.get("state") or "IDLE")
        if bool(current_runtime.get("running")):
            progress = float(current_runtime.get("overall_progress", current_runtime.get("progress", 0.0)) or 0.0)
            current = int(current_runtime.get("current") or current_runtime.get("processed_symbols") or 0)
            total = int(current_runtime.get("total") or current_runtime.get("total_symbols") or 0)
            st.success("추천 작업 실행 중")
            st.progress(progress, text=str(current_runtime.get("message") or f"처리 {current:,}/{total:,}"))
        elif state == "COMPLETED":
            st.success(f"추천 완료 · {int(current_runtime.get('recommendation_count') or 0)}건")
        elif state in {"FAILED", "STALE", "CANCELLED"}:
            st.warning(str(current_runtime.get("error_message") or current_runtime.get("message") or state))
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def _controller_selection(recommendations, market: str):
    key = f"workbench_selected_{market}"
    tickers = [str(row["ticker"]) for row in recommendations]
    if st.session_state.get(key) not in tickers:
        st.session_state[key] = tickers[0]
    return next(row for row in recommendations if str(row["ticker"]) == st.session_state[key])


def _render_controller(st, recommendations, selected, market: str) -> None:
    st.markdown(
        """
        <style>
        .wb-mobile-cards{display:none}
        @media(max-width:640px){
          .wb-desktop-table{display:none!important}
          .wb-mobile-cards{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;max-height:154px;overflow:auto;padding-right:1px}
          .wb-mobile-card-wrap{margin:0}
          .wb-mobile-card-wrap .stButton>button{
            min-height:44px!important;padding:5px 6px!important;border-radius:7px!important;
            text-align:left!important;justify-content:flex-start!important;background:#fff!important;
            border:1px solid #dbe6f0!important;color:#18324a!important;font-size:9px!important;line-height:1.15!important;
          }
          .wb-mobile-card-wrap.selected .stButton>button{
            background:#edf5ff!important;border-color:#8fbbe7!important;box-shadow:inset 2px 0 0 #2f78d6!important;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<div class="wb-desktop-table">', unsafe_allow_html=True)
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
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="wb-mobile-cards">', unsafe_allow_html=True)
    for row in recommendations[:12]:
        ticker = str(row["ticker"])
        is_selected = ticker == str(selected["ticker"])
        rank_no = int(row["rank_no"])
        weekly = float(row["weekly_similarity"])
        sto = float(row["sto_similarity"])
        label = f"#{rank_no} {row['symbol']}\n주봉 {weekly:.1f}% · STO {sto:.1f}%"
        st.markdown(
            f'<div class="wb-mobile-card-wrap {"selected" if is_selected else ""}">',
            unsafe_allow_html=True,
        )
        if st.button(
            label,
            key=f"workbench_mobile_card_{market}_{ticker}",
            use_container_width=True,
        ):
            st.session_state[f"workbench_selected_{market}"] = ticker
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.caption(f"현재 선택: {selected['symbol']}")