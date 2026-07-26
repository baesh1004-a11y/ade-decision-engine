from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from dashboard import recommendation_workbench_v2_app as base
from dashboard.daily_center_app import _initialize_widget_state, _persist_widget_state
from dashboard.design_system import apply_design_system, step_header
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
        @media(max-width:640px){
          [data-testid="stAppViewContainer"] .main .block-container{padding:8px 14px 28px!important}
          .wb-title{padding:4px 0 8px;border-bottom:1px solid #e2e8f0}
          .wb-title h1{margin:0;font-size:20px;line-height:1.2;color:#0f172a}
          .wb-title p{margin:4px 0 0;font-size:11px;line-height:1.35;color:#64748b}
          .wb-market [data-testid="stSegmentedControl"]{width:100%!important;margin:6px 0 4px}
          .wb-market [data-testid="stSegmentedControl"]>div{display:grid!important;grid-template-columns:1fr 1fr!important;width:100%!important}
          .wb-market button{width:100%!important;min-height:36px!important;font-size:12px!important}
          .wb-summary{display:block;margin:6px 0 8px;border-top:1px solid #e2e8f0}
          .wb-summary-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid #e2e8f0}
          .wb-summary-row span{font-size:11px;color:#64748b}
          .wb-summary-row strong{font-size:13px;color:#0f172a;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
          .wb-context{padding:6px 0 8px;border-bottom:1px solid #e2e8f0}
          .wb-context>div{font-size:11px;color:#334155;font-weight:700}
          .wb-context details{margin-top:3px}
          .wb-context summary{font-size:10px;color:#64748b}
          .wb-context small{display:block;margin-top:4px;font-size:9px;line-height:1.35;color:#64748b;word-break:break-all}
          .wb-settings [data-testid="stExpander"]{margin:0 0 8px!important}
          .wb-settings [data-testid="stExpander"] summary{min-height:40px!important;padding:0!important}
          .wb-settings [data-testid="stExpander"] summary [class*="material-symbols"]{display:none!important}
          .wb-settings [data-testid="stExpander"] summary p{font-size:12px!important}
          .wb-settings div[data-testid="stHorizontalBlock"]{display:block!important}
          .wb-settings div[data-testid="stColumn"]{display:block!important;width:100%!important;min-width:0!important;flex:none!important;margin-bottom:6px!important}
          .wb-settings label{font-size:10px!important}
          .wb-settings input{min-height:36px!important;font-size:12px!important}
          .wb-settings .stButton>button{min-height:38px!important;font-size:12px!important}
          .wb-section{margin:12px 0 0}
          .wb-section>.ade-step{margin:0 0 6px!important;padding:0!important;border:0!important}
          .wb-section>.ade-step p{display:none!important}
          .wb-section>.ade-step h3{font-size:15px!important;margin:0!important}
          .wb-section div[data-testid="stHorizontalBlock"]{display:block!important}
          .wb-section div[data-testid="stColumn"]{display:block!important;width:100%!important;min-width:0!important;max-width:none!important;flex:none!important;margin:0 0 6px!important}
          .wb-section div[data-testid="stDataFrame"]{width:100%!important;max-height:260px!important}
          .wb-section [data-testid="stPlotlyChart"]{width:100%!important;min-height:240px!important}
          .wb-desktop-table{display:none!important}
          .wb-mobile-cards{display:block!important}
          .wb-mobile-card-wrap{border-bottom:1px solid #e2e8f0}
          .wb-mobile-card-wrap .stButton>button{min-height:46px!important;padding:8px 4px!important;border:0!important;border-radius:0!important;background:#fff!important;color:#18324a!important;justify-content:flex-start!important;text-align:left!important;font-size:12px!important;box-shadow:none!important}
          .wb-mobile-card-wrap.selected .stButton>button{background:#eff6ff!important;color:#1d4ed8!important;box-shadow:inset 3px 0 0 #2563eb!important}
          .selected-stock{padding:8px 0!important;margin:0!important;border-bottom:1px solid #e2e8f0!important}
          .selected-stock b{font-size:14px!important}
          .selected-stock small,.selected-stock span{font-size:11px!important}
          .mini-card,.order-card,.order-count{padding:7px 0!important;border-bottom:1px solid #e2e8f0!important}
        }
        @media(min-width:641px){
          .wb-mobile-only{display:none!important}
          .wb-desktop-table{display:block!important}
          .wb-mobile-cards{display:none!important}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="wb-title"><h1>투자 워크벤치</h1><p>추천 종목을 선택하고 분석·검증·주문으로 연결합니다.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="wb-market">', unsafe_allow_html=True)
    market = st.segmented_control(
        "시장",
        options=["kr", "us"],
        default="kr",
        format_func=lambda value: "🇰🇷 한국" if value == "kr" else "🇺🇸 미국",
        label_visibility="collapsed",
    )
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
        _render_generation_controls(profile, runtime, context)

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
            f'''<div class="wb-summary">
              <div class="wb-summary-row"><span>추천</span><strong>{len(recommendations)}건</strong></div>
              <div class="wb-summary-row"><span>환경 조언</span><strong>{len(context.validations)}건</strong></div>
              <div class="wb-summary-row"><span>선택 종목</span><strong>{selected['symbol']}</strong></div>
            </div>
            <div class="wb-context"><div>추천 {len(recommendations)} · 조언 {len(context.validations)} · 주문 {len(context.current_orders)}</div>
            <details><summary>실행 정보 보기</summary><small>run_id {context.run_id}<br>최근 실행 {context.finished_at or '-'} · {context.run_type or '-'}</small></details></div>''',
            unsafe_allow_html=True,
        )

        st.markdown('<section class="wb-section">', unsafe_allow_html=True)
        step_header(1, "추천 목록", "종목을 선택합니다.")
        _render_controller(recommendations, selected, profile.code)
        st.markdown('</section>', unsafe_allow_html=True)

        st.markdown('<section class="wb-section">', unsafe_allow_html=True)
        step_header(2, "분석 및 검증", "차트와 검증 결과를 확인합니다.")
        base._comparison_panel(
            st,
            selected,
            current,
            historical,
            pattern,
            payload,
            profile.code,
            profile.db_path,
            context.run_id,
            validation,
        )
        st.markdown('</section>', unsafe_allow_html=True)

        st.markdown('<section class="wb-section">', unsafe_allow_html=True)
        step_header(3, "주문", "주문 화면으로 연결합니다.")
        base._order_panel(st, selected, profile.code, validation, context)
        st.markdown('</section>', unsafe_allow_html=True)
    finally:
        conn.close()


def _render_generation_controls(profile, runtime, context) -> None:
    fallback = context.parameters if context is not None and hasattr(context, "parameters") else None
    _initialize_widget_state(st, profile.code, fallback)

    years_key = f"{profile.code}_replay_years"
    pool_key = f"{profile.code}_weekly_pool"
    weekly_key = f"{profile.code}_weekly"
    sto_key = f"{profile.code}_sto"
    top_key = f"{profile.code}_top_n"

    st.markdown('<div class="wb-settings">', unsafe_allow_html=True)
    with st.expander("추천 설정", expanded=False):
        st.number_input("과거 패턴 기간(년)", 1, 10, step=1, key=years_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("비교할 과거 패턴 수", 10, 1000, step=10, key=pool_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("최소 주봉 유사도", 0.0, 100.0, step=1.0, key=weekly_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("STO 통과 기준", 0.0, 100.0, step=1.0, key=sto_key, on_change=_persist_widget_state, args=(st, profile.code))
        st.number_input("저장할 추천 종목 수", 1, 50, step=1, key=top_key, on_change=_persist_widget_state, args=(st, profile.code))

        running = bool(runtime.get("running"))
        if st.button("추천 생성 및 저장", type="primary", use_container_width=True, disabled=running, key=f"workbench_run_{profile.code}"):
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
                st.warning("같은 시장의 추천 작업이 이미 실행 중입니다.")

        if st.button("새로고침", use_container_width=True, key=f"workbench_refresh_{profile.code}"):
            st.rerun()

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


def _controller_selection(recommendations, market: str):
    key = f"workbench_selected_{market}"
    tickers = [str(row["ticker"]) for row in recommendations]
    if st.session_state.get(key) not in tickers:
        st.session_state[key] = tickers[0]
    return next(row for row in recommendations if str(row["ticker"]) == st.session_state[key])


def _render_controller(recommendations, selected, market: str) -> None:
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
        label = f"#{rank_no} {row['symbol']} · 주봉 {weekly:.1f}% · STO {sto:.1f}%"
        st.markdown(f'<div class="wb-mobile-card-wrap {"selected" if is_selected else ""}">', unsafe_allow_html=True)
        if st.button(label, key=f"workbench_mobile_card_{market}_{ticker}", use_container_width=True):
            st.session_state[f"workbench_selected_{market}"] = ticker
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    run()
