from __future__ import annotations

import json
import sqlite3

import pandas as pd
import plotly.graph_objects as go

from maintenance.recommendation_runner import get_status, start_job
from markets.profiles import get_market_profile


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="AI 의사결정 엔진 대시보드", page_icon="🧠", layout="wide")
    _style(st)

    title_col, market_col = st.columns([5, 1])
    with title_col:
        st.markdown(
            """
            <div class="page-title">
              <h1>AI 의사결정 엔진 대시보드</h1>
              <p>주봉 유사도로 순위를 정하고 STO는 통과 여부만 검증합니다.</p>
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
        )

    profile = get_market_profile(str(market or "kr"))
    if not profile.db_path.exists():
        st.error(f"{profile.db_path}가 없습니다.")
        return

    conn = sqlite3.connect(str(profile.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        recommendations, run_info = _latest_recommendations(conn, profile.code)
        validations = _latest_validations(conn)
        orders = _order_summary(conn)
        runtime = get_status(profile.code)

        _render_kpis(st, recommendations, validations, orders, run_info)
        _render_generation_controls(st, profile, runtime)

        if not recommendations:
            st.info("저장된 추천 결과가 없습니다. 추천 생성 버튼을 먼저 실행하세요.")
            return

        selected = _selected_recommendation(st, recommendations, profile.code)
        payload = _safe_json(selected["payload_json"])
        _, pattern = _selected_pattern(conn, payload)
        current = _current_bars(conn, profile.code, str(selected["ticker"]), profile.price_source)
        historical = _pattern_bars(conn, pattern)
        validation = validations.get(str(selected["ticker"]))

        step1, step2, step3, step4 = st.columns([1.25, 1.55, 1.05, 1.2], gap="medium")
        with step1:
            _step_title(st, 1, "추천 생성", "주봉 유사도 순으로 추천합니다.")
            _recommendation_table(st, recommendations, selected)
        with step2:
            _step_title(st, 2, "추천 근거 비교", "현재와 과거 급등 직전 120일을 비교합니다.")
            _comparison_panel(st, selected, current, historical, pattern, payload)
        with step3:
            _step_title(st, 3, "추천 검증", "STO 통과와 시장·업종·위험을 확인합니다.")
            _validation_panel(st, selected, validation)
        with step4:
            _step_title(st, 4, "주문 관리", "사용자 승인 후 주문합니다.")
            _order_panel(st, selected, profile.code, validation, orders)

        bottom_left, bottom_center, bottom_right = st.columns([1.4, 1, 1], gap="medium")
        with bottom_left:
            _panel_title(st, "과거 급등 사례")
            _evidence_table(st, conn, payload)
        with bottom_center:
            _panel_title(st, "추천 근거")
            _reason_panel(st, payload, pattern)
        with bottom_right:
            _panel_title(st, "보유 및 성과 관리")
            _performance_panel(st, conn, orders)
    finally:
        conn.close()


def _render_kpis(st, recommendations, validations, orders, run_info) -> None:
    buy_count = sum(1 for row in validations.values() if str(row.get("decision")) == "FINAL BUY")
    watch_count = sum(1 for row in validations.values() if str(row.get("decision")) == "BUY WATCH")
    avg_weekly = (
        sum(float(row["weekly_similarity"]) for row in recommendations) / len(recommendations)
        if recommendations else 0.0
    )
    cards = [
        ("오늘 추천 종목", f"{len(recommendations)}개", "최신 추천 실행"),
        ("평균 주봉 유사도", f"{avg_weekly:.1f}%", "추천 순위 기준"),
        ("매수 검토", f"{buy_count}개", "검증 통과 후보"),
        ("관찰 종목", f"{watch_count}개", "추가 확인 필요"),
        ("주문 대기", f"{orders['pending']}건", "승인 전 요청"),
        ("최근 실행", str(run_info.get("finished_at") or "없음")[:16], str(run_info.get("run_type") or "-")),
    ]
    cols = st.columns(6, gap="small")
    for col, (label, value, note) in zip(cols, cards):
        col.markdown(
            f'<div class="kpi-card"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>',
            unsafe_allow_html=True,
        )


def _render_generation_controls(st, profile, runtime) -> None:
    with st.expander("추천 생성 설정", expanded=False):
        c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1, 1.4])
        years = c1.number_input("과거 기간(년)", 1, 10, 2, key=f"wb3_{profile.code}_years")
        pool = c2.number_input("과거 패턴 수", 10, 1000, 100, 10, key=f"wb3_{profile.code}_pool")
        weekly = c3.number_input("최소 주봉", 0.0, 100.0, 85.0, 1.0, key=f"wb3_{profile.code}_weekly")
        sto = c4.number_input("STO 통과 기준", 0.0, 100.0, 85.0, 1.0, key=f"wb3_{profile.code}_sto")
        top_n = c5.number_input("추천 수", 1, 50, 20, key=f"wb3_{profile.code}_top")
        running = bool(runtime.get("running"))
        if c6.button("추천 생성 및 저장", type="primary", use_container_width=True, disabled=running):
            if start_job(
                profile.code,
                profile.db_path,
                top_n=int(top_n),
                weekly_pool_n=int(pool),
                candidate_years=int(years),
                use_recent_replay=True,
                use_weekly_filter=True,
                min_weekly_similarity=float(weekly),
                use_sto_filter=True,
                min_sto_similarity=float(sto),
            ):
                st.rerun()
        st.info("추천 순위는 주봉 유사도만 사용합니다. STO는 기준 이상인지 통과 여부만 확인합니다.")
        if running:
            st.progress(float(runtime.get("progress", 0.0) or 0.0), text=str(runtime.get("message", "추천 계산 중")))


def _selected_recommendation(st, recommendations, market: str):
    key = f"workbench_selected_{market}"
    tickers = [str(row["ticker"]) for row in recommendations]
    if st.session_state.get(key) not in tickers:
        st.session_state[key] = tickers[0]
    labels = {
        str(row["ticker"]): f"#{int(row['rank_no'])} {_row_name(row)} ({row['ticker']})"
        for row in recommendations
    }
    ticker = st.selectbox(
        "분석 종목 선택",
        tickers,
        index=tickers.index(st.session_state[key]),
        format_func=lambda value: labels[value],
        key=f"workbench_select_{market}",
    )
    st.session_state[key] = ticker
    return next(row for row in recommendations if str(row["ticker"]) == ticker)


def _recommendation_table(st, recommendations, selected) -> None:
    rows = []
    selected_ticker = str(selected["ticker"])
    for row in recommendations[:10]:
        ticker = str(row["ticker"])
        rows.append({
            "": "▶" if ticker == selected_ticker else "",
            "순위": int(row["rank_no"]),
            "종목명": _row_name(row),
            "코드": ticker,
            "주봉": round(float(row["weekly_similarity"]), 1),
            "STO": round(float(row["sto_similarity"]), 1),
            "STO 통과": "PASS",
        })
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "": st.column_config.TextColumn("", width="small"),
            "순위": st.column_config.NumberColumn("순위", width="small"),
            "종목명": st.column_config.TextColumn("종목명", width="medium"),
            "코드": st.column_config.TextColumn("코드", width="small"),
            "주봉": st.column_config.NumberColumn("주봉", format="%.1f%%"),
            "STO": st.column_config.NumberColumn("STO", format="%.1f%%"),
            "STO 통과": st.column_config.TextColumn("STO", width="small"),
        },
    )


def _comparison_panel(st, selected, current, historical, pattern, payload) -> None:
    name = _row_name(selected)
    st.markdown(f'<div class="selected-stock"><b>{name}</b><span>{selected["ticker"]}</span></div>', unsafe_allow_html=True)
    if current.empty or historical.empty:
        st.warning("비교 가능한 가격 데이터가 부족합니다.")
        return
    chart_col, sto_col = st.columns(2, gap="small")
    with chart_col:
        st.caption("현재 120일 vs 과거 120일")
        st.plotly_chart(_price_chart(current, historical, selected, pattern), use_container_width=True, config={"displayModeBar": False})
    with sto_col:
        st.caption("STO 흐름 비교")
        st.plotly_chart(_sto_chart(current, historical), use_container_width=True, config={"displayModeBar": False})
    metrics = st.columns(4, gap="small")
    values = [
        ("순위점수", float(selected["weekly_similarity"]), "%"),
        ("주봉", float(selected["weekly_similarity"]), "%"),
        ("STO", float(selected["sto_similarity"]), "%"),
        ("사례", len(payload.get("replay_matches") or []), "건"),
    ]
    for col, (label, value, suffix) in zip(metrics, values):
        display = f"{value:.1f}{suffix}" if suffix == "%" else f"{int(value)}{suffix}"
        col.markdown(f'<div class="mini-card"><span>{label}</span><b>{display}</b></div>', unsafe_allow_html=True)


def _validation_panel(st, selected, validation) -> None:
    decision = str(validation.get("decision")) if validation else "미검증"
    label = {"FINAL BUY": "매수 검토", "BUY WATCH": "관찰", "HOLD": "보류", "PASS": "제외"}.get(decision, decision)
    market = float(validation.get("market_score", 0)) if validation else 0
    sector = float(validation.get("sector_score", 0)) if validation else 0
    risk = float(validation.get("risk_score", 0)) if validation else 0
    st.markdown(f'<div class="validation-result"><span>검증 결과</span><strong>{label}</strong></div>', unsafe_allow_html=True)
    checks = [
        ("주봉 순위점수", f"{float(selected['weekly_similarity']):.1f}%", "good"),
        ("STO 필터", "PASS", "good"),
        ("시장 레이더", _status_text(market), _tone(market)),
        ("업종 레이더", _status_text(sector), _tone(sector)),
        ("위험 관리", _risk_text(risk), _risk_tone(risk)),
    ]
    for title, value, tone in checks:
        st.markdown(f'<div class="validation-row"><b>{title}</b><span class="{tone}">{value}</span></div>', unsafe_allow_html=True)
    if not validation:
        st.caption("추천 검증을 실행하면 시장·업종·위험 결과가 연결됩니다.")


def _order_panel(st, selected, market: str, validation, orders) -> None:
    name = _row_name(selected)
    decision = str(validation.get("decision")) if validation else "미검증"
    eligible = decision in {"FINAL BUY", "BUY WATCH"}
    state = "주문 가능" if eligible else "검증 필요"
    st.markdown(
        f'<div class="order-highlight"><span>{name}</span><b>{selected["ticker"]}</b><strong>{state}</strong></div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    c1.metric("주문 대기", orders["pending"])
    c2.metric("검증 상태", "완료" if validation else "대기")
    target = "pages/9_Trading_Desk.py" if market == "kr" else "pages/12_US_Trading_Desk.py"
    st.page_link(target, label="주문관리 열기", icon="🛒", use_container_width=True)
    st.caption("실제 주문은 주문관리 화면에서 최종 승인합니다.")


def _evidence_table(st, conn, payload) -> None:
    rows = []
    for item in (payload.get("replay_matches") or [])[:6]:
        pattern = conn.execute("SELECT * FROM surge_patterns WHERE pattern_id=?", (item.get("event_id"),)).fetchone()
        if pattern is None:
            continue
        rows.append({
            "과거 종목": pattern["name"] or pattern["ticker"],
            "유형": pattern["surge_class"],
            "30% 도달": f"{int(pattern['target_hit_day'])}일",
            "주봉": round(float(item.get("weekly_similarity", 0)), 1),
            "STO": round(float(item.get("sto_similarity", 0)), 1),
            "최대 상승": f"+{float(pattern['surge_return_pct']):.1f}%",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=265)
    else:
        st.info("저장된 과거 매칭 사례가 없습니다.")


def _reason_panel(st, payload, pattern) -> None:
    reasons = [str(item) for item in payload.get("reasons") or []]
    if pattern is not None:
        reasons.insert(0, f"대표 사례는 {pattern['surge_class']} 유형이며 {int(pattern['target_hit_day'])}거래일에 30% 상승에 도달했습니다.")
    for reason in reasons[:5]:
        st.markdown(f'<div class="reason-item">{reason}</div>', unsafe_allow_html=True)


def _performance_panel(st, conn, orders) -> None:
    holdings = _count_rows(conn, ["positions", "portfolio_positions", "holdings"])
    executions = _count_rows(conn, ["trade_execution_events"])
    c1, c2 = st.columns(2)
    c1.metric("보유 종목", holdings)
    c2.metric("체결 기록", executions)
    st.markdown(
        f'<div class="performance-card"><span>현재 주문 흐름</span><b>대기 {orders["pending"]}건</b><small>포트폴리오와 성과 화면에서 후속 관리</small></div>',
        unsafe_allow_html=True,
    )
    st.page_link("pages/1_ADE_Cockpit.py", label="포트폴리오 현황", icon="💼", use_container_width=True)
    st.page_link("pages/6_Feedback.py", label="성과 분석", icon="📈", use_container_width=True)


def _step_title(st, number: int, title: str, description: str) -> None:
    st.markdown(
        f'<div class="step-header"><span>{number}</span><div><b>{title}</b><small>{description}</small></div></div>',
        unsafe_allow_html=True,
    )


def _panel_title(st, title: str) -> None:
    st.markdown(f'<div class="panel-title">{title}</div>', unsafe_allow_html=True)


def _row_name(row) -> str:
    direct = row["name"] if "name" in row.keys() else None
    if direct and str(direct).strip():
        return str(direct).strip()
    payload = _safe_json(row["payload_json"] if "payload_json" in row.keys() else None)
    payload_name = payload.get("name")
    return str(payload_name).strip() if payload_name and str(payload_name).strip() else str(row["ticker"])


def _latest_recommendations(conn, market):
    if not _table_exists(conn, "daily_recommendations"):
        return [], {}
    run = conn.execute(
        """SELECT r.* FROM recommendation_runs r WHERE r.status='COMPLETED'
        AND EXISTS(SELECT 1 FROM daily_recommendations d WHERE d.run_id=r.run_id AND d.market=?)
        ORDER BY r.started_at DESC LIMIT 1""",
        (market,),
    ).fetchone()
    if run is None:
        return [], {}
    rows = conn.execute(
        "SELECT * FROM daily_recommendations WHERE run_id=? AND market=? ORDER BY rank_no",
        (run["run_id"], market),
    ).fetchall()
    return rows, dict(run)


def _latest_validations(conn):
    if not _table_exists(conn, "final_decisions"):
        return {}
    run = conn.execute("SELECT source_run_id FROM final_decisions ORDER BY created_at DESC LIMIT 1").fetchone()
    if run is None:
        return {}
    rows = conn.execute("SELECT * FROM final_decisions WHERE source_run_id=?", (run["source_run_id"],)).fetchall()
    return {str(row["ticker"]): dict(row) for row in rows}


def _order_summary(conn):
    if not _table_exists(conn, "trade_order_requests"):
        return {"pending": 0}
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM trade_order_requests WHERE status IN ('PENDING_APPROVAL','PENDING','READY','APPROVED')"
    ).fetchone()
    return {"pending": int(row["count"] or 0)}


def _selected_pattern(conn, payload):
    matches = payload.get("replay_matches") or []
    if not matches:
        return None, None
    match = matches[0]
    pattern = conn.execute("SELECT * FROM surge_patterns WHERE pattern_id=?", (match.get("event_id"),)).fetchone()
    return match, pattern


def _current_bars(conn, market, ticker, source):
    rows = conn.execute(
        """SELECT trade_date AS Date, open AS Open, high AS High, low AS Low, close AS Close, volume AS Volume
        FROM price_bars WHERE market=? AND ticker=? AND source=? ORDER BY trade_date DESC LIMIT 120""",
        (market, ticker, source),
    ).fetchall()
    return pd.DataFrame([dict(row) for row in reversed(rows)])


def _pattern_bars(conn, pattern):
    if pattern is None:
        return pd.DataFrame()
    rows = conn.execute("SELECT * FROM surge_pattern_bars WHERE pattern_id=? ORDER BY day_index", (pattern["pattern_id"],)).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _price_chart(current, historical, selected, pattern):
    current_values = (current["Close"].astype(float) / float(current.iloc[0]["Close"]) - 1) * 100
    historical_values = (historical["close"].astype(float) / float(historical.iloc[0]["close"]) - 1) * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=current_values, mode="lines", name=f"현재 {_row_name(selected)}", line=dict(width=3)))
    fig.add_trace(go.Scatter(y=historical_values, mode="lines", name=f"과거 {pattern['name'] or pattern['ticker']}", line=dict(width=2, dash="dot")))
    fig.update_layout(height=245, margin=dict(l=8, r=8, t=25, b=8), hovermode="x unified", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.75)", legend=dict(orientation="h", y=1.16), yaxis_title="등락률(%)")
    return fig


def _sto_chart(current, historical):
    current_s = _stochastic(current["Close"].astype(float))
    historical_s = _stochastic(historical["close"].astype(float))
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=current_s, mode="lines", name="현재 STO", line=dict(width=3)))
    fig.add_trace(go.Scatter(y=historical_s, mode="lines", name="과거 STO", line=dict(width=2, dash="dot")))
    fig.add_hline(y=80, line_dash="dash", line_width=1)
    fig.add_hline(y=20, line_dash="dash", line_width=1)
    fig.update_layout(height=245, margin=dict(l=8, r=8, t=25, b=8), yaxis=dict(range=[0, 100]), hovermode="x unified", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.75)", legend=dict(orientation="h", y=1.16))
    return fig


def _stochastic(close: pd.Series, period: int = 14):
    low = close.rolling(period, min_periods=1).min()
    high = close.rolling(period, min_periods=1).max()
    return ((close - low) / (high - low).replace(0, 1) * 100).fillna(50)


def _safe_json(value):
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _table_exists(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _count_rows(conn, candidates):
    for table in candidates:
        if _table_exists(conn, table):
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
            return int(row["count"] or 0)
    return 0


def _status_text(score):
    return "양호" if score >= 70 else "보통" if score >= 45 else "주의"


def _risk_text(score):
    return "낮음" if score >= 70 else "보통" if score >= 45 else "높음"


def _tone(score):
    return "good" if score >= 70 else "warn" if score >= 45 else "bad"


def _risk_tone(score):
    return _tone(score)


def _style(st) -> None:
    st.markdown(
        """
        <style>
        :root{--navy:#09243d;--blue:#2778da;--ink:#152b42;--muted:#718397;--line:#dbe6ef;--panel:#fff;--green:#16a36a;--amber:#d79518;--red:#e55353}
        .stApp{background:linear-gradient(135deg,#f8fbfe,#eef4fa 55%,#fbfdff);color:var(--ink)}
        .block-container{max-width:1900px;padding:.7rem 1.2rem 2rem}
        [data-testid="stSidebar"]{background:linear-gradient(180deg,#08223a,#0c2c49)}
        [data-testid="stSidebar"] *{color:#edf7ff!important}
        .page-title h1{margin:0;font-size:28px}.page-title p{margin:2px 0 10px;color:var(--muted)}
        .kpi-card{min-height:105px;padding:16px;border-radius:16px;background:var(--panel);border:1px solid var(--line);box-shadow:0 7px 23px rgba(35,72,105,.06)}
        .kpi-card span,.kpi-card small{display:block;color:var(--muted)}.kpi-card strong{display:block;font-size:25px;margin:8px 0 4px}
        .step-header{display:flex;gap:10px;padding:13px 14px;margin-top:14px;border:1px solid var(--line);border-radius:14px 14px 0 0;background:linear-gradient(135deg,#fff,#f2f7fc)}
        .step-header>span{display:flex;align-items:center;justify-content:center;width:29px;height:29px;border-radius:8px;background:#2778da;color:white;font-weight:900}.step-header b{display:block;color:#165ea9}.step-header small{display:block;color:var(--muted)}
        .panel-title{margin-top:15px;padding:12px 14px;border-radius:13px 13px 0 0;background:white;border:1px solid var(--line);font-weight:850;color:#174f84}
        .selected-stock{display:flex;justify-content:space-between;padding:10px 12px;margin:9px 0;border-radius:11px;background:#eef6ff}.selected-stock span{color:var(--muted)}
        .mini-card,.validation-result,.order-highlight,.performance-card,.reason-item{padding:11px 12px;border-radius:11px;background:white;border:1px solid var(--line);margin-bottom:8px}
        .mini-card span,.validation-result span{display:block;color:var(--muted);font-size:11px}.mini-card b,.validation-result strong{display:block;font-size:17px;margin-top:3px}
        .validation-row{display:flex;justify-content:space-between;padding:11px 12px;margin-top:7px;border-radius:10px;background:white;border:1px solid var(--line)}
        .good{color:var(--green);font-weight:850}.warn{color:var(--amber);font-weight:850}.bad{color:var(--red);font-weight:850}
        </style>
        """,
        unsafe_allow_html=True,
    )
