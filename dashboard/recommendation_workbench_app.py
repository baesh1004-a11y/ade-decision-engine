from __future__ import annotations

import json
import sqlite3

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
        payload = _safe_json(selected.get("payload_json"))
        _, pattern = _selected_pattern(conn, payload)
        current = _current_bars(conn, profile.code, str(selected["ticker"]), profile.price_source)
        historical = _pattern_bars(conn, pattern)
        validation = validations.get(str(selected["ticker"]))

        # 추천 근거 비교 영역을 가장 크게 배치한다.
        step1, step2, step3, step4 = st.columns([1.15, 2.55, 1.0, 1.05], gap="medium")
        with step1:
            _step_title(st, 1, "추천 생성", "종목명과 주봉 유사도 순으로 표시합니다.")
            _recommendation_table(st, recommendations, selected)
        with step2:
            _step_title(st, 2, "추천 근거 비교", "캔들·거래량·볼린저밴드·STO로 현재 흐름을 확인합니다.")
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
        years = c1.number_input("과거 기간(년)", 1, 10, 2, key=f"wb4_{profile.code}_years")
        pool = c2.number_input("과거 패턴 수", 10, 1000, 100, 10, key=f"wb4_{profile.code}_pool")
        weekly = c3.number_input("최소 주봉", 0.0, 100.0, 85.0, 1.0, key=f"wb4_{profile.code}_weekly")
        sto = c4.number_input("STO 통과 기준", 0.0, 100.0, 85.0, 1.0, key=f"wb4_{profile.code}_sto")
        top_n = c5.number_input("추천 수", 1, 50, 20, key=f"wb4_{profile.code}_top")
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
    for row in recommendations[:20]:
        ticker = str(row["ticker"])
        rows.append({
            "": "▶" if ticker == selected_ticker else "",
            "순위": int(row["rank_no"]),
            "종목명": _row_name(row),
            "코드": ticker,
            "주봉": round(float(row["weekly_similarity"]), 1),
            "STO": round(float(row["sto_similarity"]), 1),
            "상태": "PASS",
        })
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        height=650,
        column_config={
            "": st.column_config.TextColumn("", width="small"),
            "순위": st.column_config.NumberColumn("순위", width="small"),
            "종목명": st.column_config.TextColumn("종목명", width="large"),
            "코드": st.column_config.TextColumn("코드", width="small"),
            "주봉": st.column_config.NumberColumn("주봉", format="%.1f%%"),
            "STO": st.column_config.NumberColumn("STO", format="%.1f%%"),
            "상태": st.column_config.TextColumn("상태", width="small"),
        },
    )


def _comparison_panel(st, selected, current, historical, pattern, payload) -> None:
    name = _row_name(selected)
    st.markdown(
        f'<div class="selected-stock"><div><b>{name}</b><small>{selected["ticker"]}</small></div>'
        f'<div><strong>주봉 {float(selected["weekly_similarity"]):.1f}%</strong>'
        f'<span>STO {float(selected["sto_similarity"]):.1f}% · PASS</span></div></div>',
        unsafe_allow_html=True,
    )
    if current.empty:
        st.warning("현재 가격 데이터가 부족합니다.")
        return

    chart_tab, compare_tab = st.tabs(["현재 종목 차트", "과거 패턴 비교"])
    with chart_tab:
        st.plotly_chart(
            _tradingview_chart(current, name),
            use_container_width=True,
            config={"displayModeBar": True, "scrollZoom": True, "responsive": True},
        )
    with compare_tab:
        if historical.empty or pattern is None:
            st.warning("비교 가능한 과거 패턴이 없습니다.")
        else:
            st.plotly_chart(
                _pattern_compare_chart(current, historical, selected, pattern),
                use_container_width=True,
                config={"displayModeBar": True, "scrollZoom": True},
            )

    metrics = st.columns(4, gap="small")
    values = [
        ("순위점수", float(selected["weekly_similarity"]), "%"),
        ("주봉", float(selected["weekly_similarity"]), "%"),
        ("STO", float(selected["sto_similarity"]), "%"),
        ("과거 사례", len(payload.get("replay_matches") or []), "건"),
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
    direct = row.get("display_name") if isinstance(row, dict) else None
    if direct and str(direct).strip() and str(direct).strip() != str(row["ticker"]):
        return str(direct).strip()
    name = row.get("name") if isinstance(row, dict) else row["name"]
    if name and str(name).strip() and str(name).strip() != str(row["ticker"]):
        return str(name).strip()
    payload = _safe_json(row.get("payload_json") if isinstance(row, dict) else row["payload_json"])
    payload_name = payload.get("name")
    if payload_name and str(payload_name).strip() and str(payload_name).strip() != str(row["ticker"]):
        return str(payload_name).strip()
    return str(row["ticker"])


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
    name_map = _symbol_name_map(conn, market)
    result = []
    for row in rows:
        item = dict(row)
        ticker = str(item["ticker"])
        existing = str(item.get("name") or "").strip()
        item["display_name"] = existing if existing and existing != ticker else name_map.get(ticker, ticker)
        result.append(item)
    return result, dict(run)


def _symbol_name_map(conn, market: str) -> dict[str, str]:
    result: dict[str, str] = {}
    candidates = [
        ("stock_universe", "ticker", "name"),
        ("kr_universe", "ticker", "name"),
        ("us_universe", "symbol", "name"),
        ("replay_events", "ticker", "name"),
        ("surge_patterns", "ticker", "name"),
    ]
    for table, ticker_col, name_col in candidates:
        if not _table_exists(conn, table):
            continue
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if ticker_col not in columns or name_col not in columns:
            continue
        where = ""
        params: tuple[object, ...] = ()
        if "market" in columns:
            where = " WHERE market=?"
            params = (market,)
        rows = conn.execute(
            f"SELECT {ticker_col} AS ticker, {name_col} AS name FROM {table}{where}",
            params,
        ).fetchall()
        for row in rows:
            ticker = str(row["ticker"] or "").strip()
            name = str(row["name"] or "").strip()
            if ticker and name and name != ticker:
                result[ticker] = name
    return result


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
    if not rows:
        rows = conn.execute(
            """SELECT trade_date AS Date, open AS Open, high AS High, low AS Low, close AS Close, volume AS Volume
            FROM price_bars WHERE market=? AND ticker=? ORDER BY trade_date DESC LIMIT 120""",
            (market, ticker),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in reversed(rows)])


def _pattern_bars(conn, pattern):
    if pattern is None:
        return pd.DataFrame()
    rows = conn.execute("SELECT * FROM surge_pattern_bars WHERE pattern_id=? ORDER BY day_index", (pattern["pattern_id"],)).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _tradingview_chart(data: pd.DataFrame, name: str) -> go.Figure:
    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna().reset_index(drop=True)

    df["SMA20"] = df["Close"].rolling(20, min_periods=1).mean()
    std20 = df["Close"].rolling(20, min_periods=1).std().fillna(0)
    df["BB_UPPER"] = df["SMA20"] + std20 * 2
    df["BB_LOWER"] = df["SMA20"] - std20 * 2
    k, d = _stochastic_ohlc(df)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=[0.62, 0.16, 0.22],
    )
    fig.add_trace(
        go.Candlestick(
            x=df["Date"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            name=name,
            increasing_line_color="#16a085", increasing_fillcolor="#16a085",
            decreasing_line_color="#ef5350", decreasing_fillcolor="#ef5350",
        ),
        row=1, col=1,
    )
    fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_UPPER"], name="BB 상단", line=dict(color="#ef5350", width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["SMA20"], name="SMA20", line=dict(color="#2962ff", width=1.7)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_LOWER"], name="BB 하단", line=dict(color="#26a69a", width=1.5), fill="tonexty", fillcolor="rgba(38,166,154,.05)"), row=1, col=1)

    volume_colors = ["#16a085" if close >= open_ else "#ef5350" for close, open_ in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df["Date"], y=df["Volume"], name="거래량", marker_color=volume_colors, opacity=0.72), row=2, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=k, name="STO %K", line=dict(color="#2962ff", width=1.7)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=d, name="STO %D", line=dict(color="#ff9800", width=1.7)), row=3, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color="#8d99a6", row=3, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="#8d99a6", row=3, col=1)

    fig.update_layout(
        height=700,
        margin=dict(l=8, r=54, t=40, b=10),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(255,255,255,.7)"),
        font=dict(color="#22364a", size=11),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(150,165,180,.16)", rangeslider_visible=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(150,165,180,.16)", side="right")
    fig.update_yaxes(range=[0, 100], row=3, col=1)
    return fig


def _pattern_compare_chart(current, historical, selected, pattern):
    current_values = (current["Close"].astype(float) / float(current.iloc[0]["Close"]) - 1) * 100
    historical_values = (historical["close"].astype(float) / float(historical.iloc[0]["close"]) - 1) * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=current_values, mode="lines", name=f"현재 {_row_name(selected)}", line=dict(width=3, color="#2962ff")))
    fig.add_trace(go.Scatter(y=historical_values, mode="lines", name=f"과거 {pattern['name'] or pattern['ticker']}", line=dict(width=2, dash="dot", color="#ef5350")))
    fig.add_hline(y=0, line_color="#8d99a6", line_width=1)
    fig.update_layout(
        height=700,
        margin=dict(l=15, r=55, t=35, b=20),
        hovermode="x unified",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend=dict(orientation="h", y=1.04),
        yaxis_title="등락률(%)",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(150,165,180,.16)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(150,165,180,.16)", side="right")
    return fig


def _stochastic_ohlc(df: pd.DataFrame, period: int = 14, smooth: int = 3):
    lowest = df["Low"].rolling(period, min_periods=1).min()
    highest = df["High"].rolling(period, min_periods=1).max()
    k = ((df["Close"] - lowest) / (highest - lowest).replace(0, 1) * 100).fillna(50)
    d = k.rolling(smooth, min_periods=1).mean()
    return k, d


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
        .block-container{max-width:2100px;padding:.55rem .8rem 2rem}
        [data-testid="stSidebar"]{background:linear-gradient(180deg,#08223a,#0c2c49)}
        [data-testid="stSidebar"] *{color:#edf7ff!important}
        .page-title h1{margin:0;font-size:28px}.page-title p{margin:2px 0 10px;color:var(--muted)}
        .kpi-card{min-height:100px;padding:15px;border-radius:15px;background:var(--panel);border:1px solid var(--line);box-shadow:0 6px 20px rgba(35,72,105,.05)}
        .kpi-card span,.kpi-card small{display:block;color:var(--muted)}.kpi-card strong{display:block;font-size:24px;margin:7px 0 4px}
        .step-header{display:flex;gap:10px;padding:13px 14px;margin-top:12px;border:1px solid var(--line);border-radius:14px 14px 0 0;background:linear-gradient(135deg,#fff,#f2f7fc)}
        .step-header>span{display:flex;align-items:center;justify-content:center;width:29px;height:29px;border-radius:8px;background:#2778da;color:white;font-weight:900}.step-header b{display:block;color:#165ea9;font-size:16px}.step-header small{display:block;color:var(--muted);line-height:1.3}
        .panel-title{margin-top:15px;padding:12px 14px;border-radius:13px 13px 0 0;background:white;border:1px solid var(--line);font-weight:850;color:#174f84}
        .selected-stock{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;margin:9px 0;border-radius:11px;background:#eef6ff;border:1px solid #d9e9f8}.selected-stock b{display:block;font-size:20px}.selected-stock small,.selected-stock span{display:block;color:var(--muted)}.selected-stock strong{display:block;color:#1976d2;font-size:16px;text-align:right}
        .mini-card,.validation-result,.order-highlight,.performance-card,.reason-item{padding:11px 12px;border-radius:11px;background:white;border:1px solid var(--line);margin-bottom:8px}
        .mini-card span,.validation-result span{display:block;color:var(--muted);font-size:11px}.mini-card b,.validation-result strong{display:block;font-size:17px;margin-top:3px}
        .validation-row{display:flex;justify-content:space-between;padding:11px 12px;margin-top:7px;border-radius:10px;background:white;border:1px solid var(--line)}
        .good{color:var(--green);font-weight:850}.warn{color:var(--amber);font-weight:850}.bad{color:var(--red);font-weight:850}
        div[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:10px;overflow:hidden}
        div[data-testid="stPlotlyChart"]{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:white}
        @media(max-width:1300px){.block-container{padding:.5rem}.selected-stock b{font-size:17px}}
        </style>
        """,
        unsafe_allow_html=True,
    )
