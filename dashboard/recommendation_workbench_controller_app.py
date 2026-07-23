from __future__ import annotations

import sqlite3

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
    _premium_style()

    title_col, market_col = st.columns([5, 1.15], vertical_alignment="center")
    with title_col:
        st.markdown(
            """
            <div class="wb-hero">
              <div class="wb-eyebrow">ADE · DECISION WORKSPACE</div>
              <div class="wb-title-row"><h1>투자 워크벤치</h1><span>LIVE WORKFLOW</span></div>
              <p>추천 생성부터 패턴 분석, 검증, 주문 준비까지 한 화면에서 연결합니다.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with market_col:
        market = st.segmented_control(
            "시장",
            options=["kr", "us"],
            default="kr",
            format_func=lambda value: "🇰🇷 한국" if value == "kr" else "🇺🇸 미국",
            label_visibility="collapsed",
            key="workbench_market_selector",
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
        _render_top_status(profile, runtime, context)
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

        base._render_kpis(st, context, recommendations)
        st.markdown('<div class="wb-section-rule"></div>', unsafe_allow_html=True)

        left, center, right = st.columns([1.18, 3.35, 1.28], gap="large")
        with left:
            _panel_header("01", "추천 랭킹", "종목 선택")
            _render_controller(recommendations, selected, profile.code)
        with center:
            _panel_header("02", "분석·검증", "현재 차트와 과거 패턴")
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
        with right:
            _panel_header("03", "판단·주문", "검증 상태와 실행")
            _render_decision_card(selected, validation, context)
            base._order_panel(st, selected, profile.code, validation, context)
    finally:
        conn.close()


def _render_top_status(profile, runtime, context) -> None:
    state = str(runtime.get("state") or "IDLE")
    running = bool(runtime.get("running"))
    state_label = "실행 중" if running else "완료" if state == "COMPLETED" else "대기"
    run_id = context.run_id if context is not None else "-"
    finished = str(context.finished_at or "-")[:16] if context is not None else "-"
    recommendation_count = context.recommendation_count if context is not None else 0
    st.markdown(
        f"""
        <div class="wb-statusbar">
          <div><span>MARKET</span><strong>{profile.name}</strong></div>
          <div><span>ENGINE</span><strong class="status-dot">{state_label}</strong></div>
          <div><span>LATEST RUN</span><strong>{run_id}</strong></div>
          <div><span>COMPLETED</span><strong>{finished}</strong></div>
          <div><span>RECOMMENDATIONS</span><strong>{recommendation_count}개</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_shared_generation_controls(profile, runtime, context) -> None:
    fallback = context.parameters if context is not None and hasattr(context, "parameters") else None
    _initialize_widget_state(st, profile.code, fallback)

    years_key = f"{profile.code}_replay_years"
    pool_key = f"{profile.code}_weekly_pool"
    weekly_key = f"{profile.code}_weekly"
    sto_key = f"{profile.code}_sto"
    top_key = f"{profile.code}_top_n"

    with st.expander("추천 생성 설정", expanded=False):
        st.caption("시장별 추천 페이지와 동일한 설정·실행 상태·결과 DB를 사용합니다.")
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
                st.warning("같은 시장의 추천 작업이 이미 실행 중입니다.")

        if b2.button("새로고침", use_container_width=True, key=f"workbench_refresh_{profile.code}"):
            st.rerun()
        target = "pages/7_Daily_Center.py" if profile.code == "kr" else "pages/10_US_Daily_Center.py"
        b3.page_link(target, label="배치 화면", use_container_width=True)

        current_runtime = get_status(profile.code)
        if bool(current_runtime.get("running")):
            progress = float(current_runtime.get("overall_progress", current_runtime.get("progress", 0.0)) or 0.0)
            current = int(current_runtime.get("current") or current_runtime.get("processed_symbols") or 0)
            total = int(current_runtime.get("total") or current_runtime.get("total_symbols") or 0)
            st.progress(progress, text=str(current_runtime.get("message") or "추천 계산 중"))
            st.caption(f"처리 {current:,}/{total:,} · 현재 종목 {current_runtime.get('current_ticker') or '-'}")
        elif str(current_runtime.get("state") or "") in {"FAILED", "STALE", "CANCELLED"}:
            st.warning(str(current_runtime.get("error_message") or current_runtime.get("message") or current_runtime.get("state")))


def _controller_selection(recommendations, market: str):
    key = f"workbench_selected_{market}"
    tickers = [str(row["ticker"]) for row in recommendations]
    if st.session_state.get(key) not in tickers:
        st.session_state[key] = tickers[0]
    return next(row for row in recommendations if str(row["ticker"]) == st.session_state[key])


def _render_controller(recommendations, selected, market: str) -> None:
    selected_ticker = str(selected["ticker"])
    for row in recommendations[:20]:
        ticker = str(row["ticker"])
        active = ticker == selected_ticker
        label = (
            f"#{int(row['rank_no']):02d}  {row['symbol']}\n"
            f"주봉 {float(row['weekly_similarity']):.1f}%  ·  STO {float(row['sto_similarity']):.1f}%"
        )
        if st.button(
            label,
            key=f"workbench_rank_{market}_{ticker}",
            type="primary" if active else "secondary",
            use_container_width=True,
        ):
            if not active:
                st.session_state[f"workbench_selected_{market}"] = ticker
                st.rerun()
    st.caption(f"현재 선택 · {selected['symbol']}")


def _panel_header(number: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="wb-panel-head">
          <span>{number}</span>
          <div><strong>{title}</strong><small>{subtitle}</small></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_decision_card(selected, validation, context) -> None:
    if validation is None:
        label = "검증 전"
        tone = "neutral"
        note = "시장·업종 환경 조언을 확인할 수 있습니다."
    else:
        decision = str(validation.get("decision"))
        label = {"FINAL BUY": "매수 검토", "BUY WATCH": "관찰", "HOLD": "보류", "PASS": "제외"}.get(decision, decision)
        tone = "positive" if decision in {"FINAL BUY", "BUY WATCH"} else "warning"
        note = "검증 결과를 참고해 주문 여부를 판단하세요."
    st.markdown(
        f"""
        <div class="wb-decision {tone}">
          <span>SELECTED ASSET</span>
          <h3>{selected['symbol']}</h3>
          <div class="wb-decision-label">{label}</div>
          <p>{note}</p>
          <small>run_id · {context.run_id}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _premium_style() -> None:
    st.markdown(
        """
        <style>
        :root{--wb-navy:#0a2340;--wb-blue:#2368d8;--wb-cyan:#dff2ff;--wb-line:#dce6f0;--wb-muted:#6d7e91;--wb-bg:#f5f8fb}
        .stApp{background:radial-gradient(circle at 82% 0%,rgba(193,229,255,.55),transparent 28%),linear-gradient(135deg,#f9fbfd 0%,#f1f5f9 52%,#f8fbfd 100%)!important}
        .block-container{max-width:1880px!important;padding:1rem 1.25rem 2.5rem!important}
        .wb-hero{padding:12px 0 8px}.wb-eyebrow{font-size:11px;letter-spacing:.22em;font-weight:800;color:#4b76a5}.wb-title-row{display:flex;align-items:center;gap:14px}.wb-title-row h1{margin:0;color:var(--wb-navy);font-size:34px;letter-spacing:-.04em}.wb-title-row span{padding:5px 9px;border-radius:999px;background:#e6f3ff;color:#246bb0;font-size:10px;font-weight:800;letter-spacing:.08em}.wb-hero p{margin:5px 0 0;color:var(--wb-muted);font-size:14px}
        .wb-statusbar{display:grid;grid-template-columns:.8fr .8fr 2fr 1.2fr 1fr;gap:1px;margin:8px 0 12px;border:1px solid var(--wb-line);border-radius:16px;overflow:hidden;background:var(--wb-line);box-shadow:0 10px 30px rgba(24,62,98,.07)}.wb-statusbar>div{padding:11px 14px;background:rgba(255,255,255,.9)}.wb-statusbar span{display:block;font-size:9px;letter-spacing:.14em;color:#8a99a8;font-weight:800}.wb-statusbar strong{display:block;margin-top:3px;color:#18334f;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.status-dot:before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:#36b37e;margin-right:7px;box-shadow:0 0 0 4px rgba(54,179,126,.12)}
        .wb-section-rule{height:1px;background:linear-gradient(90deg,transparent,#d6e1eb 15%,#d6e1eb 85%,transparent);margin:14px 0 2px}
        .wb-panel-head{display:flex;align-items:center;gap:10px;padding:12px 14px;margin:10px 0 8px;border:1px solid rgba(214,226,237,.95);border-radius:15px;background:rgba(255,255,255,.78);backdrop-filter:blur(14px);box-shadow:0 8px 24px rgba(25,60,95,.06)}.wb-panel-head>span{display:flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:11px;background:linear-gradient(145deg,#153c67,#2d72c9);color:white;font-size:11px;font-weight:900;letter-spacing:.05em}.wb-panel-head strong{display:block;color:#102c49;font-size:15px}.wb-panel-head small{display:block;color:#8291a0;font-size:11px;margin-top:1px}
        div[data-testid="stButton"] button{border-radius:12px!important;min-height:52px!important;justify-content:flex-start!important;text-align:left!important;padding:10px 12px!important;font-weight:700!important;line-height:1.35!important;box-shadow:none!important;transition:transform .16s ease,border-color .16s ease,box-shadow .16s ease!important}.stButton button[kind="secondary"]{background:rgba(255,255,255,.84)!important;border:1px solid #dce6ef!important;color:#263f59!important}.stButton button[kind="secondary"]:hover{transform:translateY(-1px);border-color:#8ab9e7!important;box-shadow:0 8px 18px rgba(31,86,137,.09)!important}.stButton button[kind="primary"]{background:linear-gradient(135deg,#12385f,#246fbd)!important;border:1px solid #2465a6!important;color:white!important;box-shadow:0 10px 22px rgba(35,104,216,.2)!important}
        .kpi-card{background:rgba(255,255,255,.86)!important;border:1px solid rgba(216,227,238,.95)!important;border-radius:16px!important;box-shadow:0 8px 24px rgba(25,60,95,.055)!important}.kpi-card strong{color:#0f2d4a!important}.selected-stock{background:linear-gradient(135deg,#f8fbff,#eaf4ff)!important;border:1px solid #d5e7f7!important;border-radius:14px!important}.mini-card,.validation-result,.order-highlight,.validation-row{background:rgba(255,255,255,.88)!important;border:1px solid #dce6ef!important;border-radius:13px!important}
        div[data-testid="stPlotlyChart"],div[data-testid="stDataFrame"]{border:1px solid #dce6ef!important;border-radius:16px!important;overflow:hidden!important;box-shadow:0 10px 28px rgba(25,60,95,.06)!important;background:white!important}
        .wb-decision{padding:18px;border:1px solid #dbe5ee;border-radius:17px;background:linear-gradient(145deg,rgba(255,255,255,.96),rgba(244,248,252,.96));box-shadow:0 12px 30px rgba(27,65,102,.08);margin-bottom:10px}.wb-decision>span{font-size:9px;letter-spacing:.16em;color:#8796a5;font-weight:800}.wb-decision h3{margin:6px 0 12px;color:#102e4c;font-size:21px}.wb-decision-label{display:inline-block;padding:7px 10px;border-radius:9px;background:#e9f2fb;color:#1f609e;font-weight:900}.wb-decision.positive .wb-decision-label{background:#e4f6ef;color:#207a59}.wb-decision.warning .wb-decision-label{background:#fff1df;color:#9b5b11}.wb-decision p{font-size:12px;color:#718193;margin:12px 0}.wb-decision small{color:#9aa7b4;font-size:10px}
        [data-testid="stExpander"]{border:1px solid #dce6ef!important;border-radius:14px!important;background:rgba(255,255,255,.72)!important;overflow:hidden!important}
        @media(max-width:1100px){.wb-statusbar{grid-template-columns:1fr 1fr}.wb-statusbar>div:nth-child(3){grid-column:span 2}.wb-title-row h1{font-size:28px}}
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    run()
