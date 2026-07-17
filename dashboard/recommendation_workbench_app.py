from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from maintenance.recommendation_runner import get_status, start_job
from markets.profiles import get_market_profile


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 추천 워크벤치", page_icon="📊", layout="wide")
    _style(st)

    market = st.segmented_control(
        "시장",
        options=["kr", "us"],
        default="kr",
        format_func=lambda value: "🇰🇷 한국" if value == "kr" else "🇺🇸 미국",
        label_visibility="collapsed",
    )
    profile = get_market_profile(str(market or "kr"))

    st.markdown(
        f"""
        <section class="hero">
          <div>
            <div class="eyebrow">ADE · {profile.code.upper()} RECOMMENDATION WORKBENCH</div>
            <h1>{profile.name} 추천 워크벤치</h1>
            <p>추천 생성부터 근거 비교, 검증, 주문 연결까지 한 화면에서 확인합니다.</p>
          </div>
          <div class="hero-badge">120일 패턴 · 주봉 60% · STO 40%</div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if not profile.db_path.exists():
        st.error(f"{profile.db_path}가 없습니다.")
        return

    conn = sqlite3.connect(str(profile.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        recommendations, run = _latest_recommendations(conn, profile.code)
        validations = _latest_validations(conn)
        orders = _order_summary(conn)
        runtime = get_status(profile.code)

        _top_metrics(st, recommendations, validations, orders, run)
        _generation_bar(st, profile, runtime)

        if not recommendations:
            st.info("저장된 추천 결과가 없습니다. 위의 추천 생성 버튼을 먼저 실행하세요.")
            return

        left, center, right = st.columns([1.15, 2.45, 1.25], gap="large")

        with left:
            selected = _recommendation_panel(st, recommendations, profile.code)

        payload = _safe_json(selected["payload_json"])
        match, pattern = _selected_pattern(conn, payload)
        current = _current_bars(conn, profile.code, str(selected["ticker"]), profile.price_source)
        historical = _pattern_bars(conn, pattern)

        with center:
            _comparison_panel(st, selected, current, historical, pattern, payload)

        with right:
            _validation_panel(st, selected, validations.get(str(selected["ticker"])), payload)
            _order_panel(st, selected, profile.code)

        st.markdown("### 과거 급등 사례와 추천 근거")
        bottom_left, bottom_right = st.columns([1.45, 1], gap="large")
        with bottom_left:
            _evidence_table(st, conn, payload)
        with bottom_right:
            _reason_panel(st, payload, pattern)
    finally:
        conn.close()


def _top_metrics(st, recommendations, validations, orders, run) -> None:
    buy_count = sum(1 for row in validations.values() if str(row.get("decision")) == "FINAL BUY")
    watch_count = sum(1 for row in validations.values() if str(row.get("decision")) == "BUY WATCH")
    avg_similarity = sum(float(row["final_similarity"]) for row in recommendations) / len(recommendations) if recommendations else 0.0
    cols = st.columns(6)
    values = [
        ("추천 종목", f"{len(recommendations)}개", "최신 완료 실행"),
        ("평균 유사도", f"{avg_similarity:.1f}%", "주봉 60% + STO 40%"),
        ("매수 검토", f"{buy_count}개", "추천 검증 결과"),
        ("관찰", f"{watch_count}개", "추가 확인 필요"),
        ("주문 대기", f"{orders['pending']}건", "승인 전 요청"),
        ("최근 실행", str(run.get("finished_at") or "없음")[:16], str(run.get("run_type") or "-")),
    ]
    for col, (label, value, sub) in zip(cols, values):
        col.markdown(f'<div class="metric-card"><span>{label}</span><strong>{value}</strong><small>{sub}</small></div>', unsafe_allow_html=True)


def _generation_bar(st, profile, runtime) -> None:
    with st.expander("추천 생성 설정", expanded=False):
        c1, c2, c3, c4, c5 = st.columns(5)
        years = c1.number_input("과거 기간(년)", 1, 10, 2, key=f"wb_{profile.code}_years")
        pool = c2.number_input("과거 패턴 수", 10, 1000, 100, 10, key=f"wb_{profile.code}_pool")
        weekly = c3.number_input("최소 주봉", 0.0, 100.0, 85.0, 1.0, key=f"wb_{profile.code}_weekly")
        sto = c4.number_input("최소 STO", 0.0, 100.0, 85.0, 1.0, key=f"wb_{profile.code}_sto")
        top_n = c5.number_input("추천 수", 1, 50, 20, key=f"wb_{profile.code}_top")
        running = bool(runtime.get("running"))
        if st.button("추천 생성 및 저장", type="primary", use_container_width=True, disabled=running):
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
        if running:
            st.progress(float(runtime.get("progress", 0.0) or 0.0), text=str(runtime.get("message", "추천 계산 중")))


def _recommendation_panel(st, recommendations, market: str):
    st.markdown("### 추천 목록")
    key = f"workbench_selected_{market}"
    tickers = [str(row["ticker"]) for row in recommendations]
    if st.session_state.get(key) not in tickers:
        st.session_state[key] = tickers[0]
    for row in recommendations[:15]:
        ticker = str(row["ticker"])
        active = ticker == st.session_state[key]
        label = f"#{int(row['rank_no'])} {row['name'] or ticker}\n유사도 {float(row['final_similarity']):.1f}% · 주봉 {float(row['weekly_similarity']):.1f}% · STO {float(row['sto_similarity']):.1f}%"
        if st.button(label, key=f"wb_rec_{market}_{ticker}", type="primary" if active else "secondary", use_container_width=True):
            st.session_state[key] = ticker
            st.rerun()
    return next(row for row in recommendations if str(row["ticker"]) == st.session_state[key])


def _comparison_panel(st, selected, current, historical, pattern, payload) -> None:
    st.markdown(f"### 현재 120일 vs 과거 급등직전 120일 · {selected['name'] or selected['ticker']}")
    if current.empty or historical.empty:
        st.warning("비교 가능한 가격 데이터가 부족합니다.")
        return
    tabs = st.tabs(["주봉 흐름", "STO 흐름"])
    with tabs[0]:
        st.plotly_chart(_price_chart(current, historical, selected, pattern), use_container_width=True, config={"displayModeBar": False})
    with tabs[1]:
        st.plotly_chart(_sto_chart(current, historical), use_container_width=True, config={"displayModeBar": False})
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("최종 유사도", f"{float(selected['final_similarity']):.1f}%")
    m2.metric("주봉 유사도", f"{float(selected['weekly_similarity']):.1f}%")
    m3.metric("STO 유사도", f"{float(selected['sto_similarity']):.1f}%")
    m4.metric("과거 사례", f"{len(payload.get('replay_matches') or [])}건")


def _validation_panel(st, selected, validation, payload) -> None:
    st.markdown("### 추천 검증")
    decision = str(validation.get("decision")) if validation else "미검증"
    label = {"FINAL BUY": "매수 검토", "BUY WATCH": "관찰", "HOLD": "보류", "PASS": "제외"}.get(decision, decision)
    market = float(validation.get("market_score", 0)) if validation else 0
    sector = float(validation.get("sector_score", 0)) if validation else 0
    risk = float(validation.get("risk_score", 0)) if validation else 0
    st.markdown(f'<div class="decision-card"><span>검증 결과</span><strong>{label}</strong><small>추천 순위와 유사도는 변경하지 않습니다.</small></div>', unsafe_allow_html=True)
    rows = [
        ("패턴", f"{float(selected['final_similarity']):.1f}%", "추천 생성 점수"),
        ("시장", _status_text(market), "시장 환경"),
        ("업종", _status_text(sector), "업종 환경"),
        ("위험", _risk_text(risk), "변동성과 위험"),
    ]
    for title, value, note in rows:
        st.markdown(f'<div class="check-row"><b>{title}</b><span>{value}</span><small>{note}</small></div>', unsafe_allow_html=True)
    if not validation:
        st.caption("추천 검증 페이지를 실행하면 시장·업종·위험 결과가 연결됩니다.")


def _order_panel(st, selected, market: str) -> None:
    st.markdown("### 주문 연결")
    st.markdown(f'<div class="order-card"><b>{selected["name"] or selected["ticker"]}</b><span>{selected["ticker"]}</span><strong>사용자 승인 후 주문</strong></div>', unsafe_allow_html=True)
    target = "pages/9_Trading_Desk.py" if market == "kr" else "pages/12_US_Trading_Desk.py"
    st.page_link(target, label="주문관리 열기", icon="🛒", use_container_width=True)


def _evidence_table(st, conn, payload) -> None:
    rows = []
    for item in payload.get("replay_matches") or []:
        pattern = conn.execute("SELECT * FROM surge_patterns WHERE pattern_id=?", (item.get("event_id"),)).fetchone()
        if pattern is None:
            continue
        rows.append({
            "과거 종목": pattern["name"] or pattern["ticker"],
            "급등 유형": pattern["surge_class"],
            "30% 도달": f"{int(pattern['target_hit_day'])}일",
            "주봉": round(float(item.get("weekly_similarity", 0)), 1),
            "STO": round(float(item.get("sto_similarity", 0)), 1),
            "최대 상승": f"+{float(pattern['surge_return_pct']):.1f}%",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("저장된 과거 매칭 사례가 없습니다.")


def _reason_panel(st, payload, pattern) -> None:
    st.markdown("#### 추천 근거")
    reasons = [str(item) for item in payload.get("reasons") or []]
    if pattern is not None:
        reasons.insert(0, f"대표 사례는 {pattern['surge_class']} 유형이며 {int(pattern['target_hit_day'])}거래일에 30% 상승에 도달했습니다.")
    for reason in reasons[:7]:
        st.markdown(f'<div class="reason-box">{reason}</div>', unsafe_allow_html=True)


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
    row = conn.execute("SELECT COUNT(*) AS count FROM trade_order_requests WHERE status IN ('PENDING','READY','APPROVED')").fetchone()
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
    fig.add_trace(go.Scatter(y=current_values, mode="lines", name=f"현재 {selected['ticker']}", line=dict(width=3)))
    fig.add_trace(go.Scatter(y=historical_values, mode="lines", name=f"과거 {pattern['ticker']}", line=dict(width=2, dash="dot")))
    fig.update_layout(height=390, margin=dict(l=15, r=15, t=35, b=15), hovermode="x unified", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.72)", legend=dict(orientation="h", y=1.12), yaxis_title="등락률(%)")
    return fig


def _sto_chart(current, historical):
    current_s = _stochastic(current["Close"].astype(float))
    historical_s = _stochastic(historical["close"].astype(float))
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=current_s, mode="lines", name="현재 STO", line=dict(width=3)))
    fig.add_trace(go.Scatter(y=historical_s, mode="lines", name="과거 STO", line=dict(width=2, dash="dot")))
    fig.add_hline(y=80, line_dash="dash", line_width=1)
    fig.add_hline(y=20, line_dash="dash", line_width=1)
    fig.update_layout(height=390, margin=dict(l=15, r=15, t=35, b=15), yaxis=dict(range=[0, 100]), hovermode="x unified", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.72)", legend=dict(orientation="h", y=1.12))
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


def _status_text(score):
    if score >= 70:
        return "양호"
    if score >= 45:
        return "보통"
    return "주의"


def _risk_text(score):
    if score >= 70:
        return "낮음"
    if score >= 45:
        return "보통"
    return "높음"


def _style(st) -> None:
    st.markdown(
        """
        <style>
        :root{--ink:#13283d;--muted:#6b7f93;--line:rgba(61,111,158,.17);--blue:#2478d4;--glass:rgba(255,255,255,.84)}
        .stApp{background:radial-gradient(circle at 8% 0%,rgba(91,169,244,.19),transparent 27%),linear-gradient(135deg,#f8fbfe,#edf4fa 52%,#fbfdff);color:var(--ink)}
        .block-container{max-width:1840px;padding-top:.8rem;padding-bottom:3rem}
        .hero{display:flex;justify-content:space-between;align-items:center;padding:24px 28px;border-radius:25px;background:linear-gradient(135deg,rgba(255,255,255,.96),rgba(234,245,255,.88));border:1px solid var(--line);box-shadow:0 18px 52px rgba(47,87,125,.11);margin-bottom:14px}
        .hero h1{margin:3px 0;font-size:34px;letter-spacing:-.045em}.hero p{margin:0;color:var(--muted)}.eyebrow{font-size:11px;letter-spacing:.15em;font-weight:850;color:#2d75b8}.hero-badge{padding:11px 15px;border-radius:999px;background:#e7f2fd;color:#276ba8;font-weight:800}
        .metric-card,.decision-card,.order-card{padding:16px 18px;border-radius:19px;background:var(--glass);border:1px solid var(--line);box-shadow:0 9px 26px rgba(50,91,128,.07)}
        .metric-card span,.decision-card span{display:block;color:var(--muted);font-size:12px;font-weight:750}.metric-card strong,.decision-card strong{display:block;font-size:25px;margin:5px 0;letter-spacing:-.04em}.metric-card small,.decision-card small{color:var(--muted)}
        .check-row{display:grid;grid-template-columns:.65fr .8fr 1fr;align-items:center;padding:12px 13px;margin-top:8px;border-radius:14px;background:rgba(255,255,255,.76);border:1px solid var(--line)}.check-row span{font-weight:850;color:#176fc1}.check-row small{color:var(--muted)}
        .order-card{margin-bottom:10px}.order-card b,.order-card span,.order-card strong{display:block}.order-card span{color:var(--muted);margin:3px 0 10px}.order-card strong{color:#16845b}
        .reason-box{padding:12px 14px;border-radius:14px;background:rgba(255,255,255,.76);border:1px solid var(--line);margin-bottom:8px;color:#28445d}
        div[data-testid="stButton"] button{border-radius:14px!important;min-height:54px;font-weight:800;white-space:pre-line;text-align:left;justify-content:flex-start}
        div[data-testid="stDataFrame"]{border-radius:17px;overflow:hidden;border:1px solid var(--line)}
        h3{letter-spacing:-.03em;color:#18344d;margin-top:1rem!important}
        @media(max-width:1000px){.block-container{padding:.65rem}.hero{display:block;padding:20px}.hero-badge{display:none}.metric-card strong{font-size:20px}}
        </style>
        """,
        unsafe_allow_html=True,
    )
