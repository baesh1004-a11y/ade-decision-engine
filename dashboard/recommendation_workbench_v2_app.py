from __future__ import annotations

import json
import sqlite3

import pandas as pd

from dashboard.charts import CHART_CONFIG, build_pattern_compare_chart, build_trading_chart
from feedback.engine import FeedbackEngine
from maintenance.recommendation_runner import get_status, start_job
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, display_symbol, normalize_ticker, resolve_name
from meta_score.dashboard import _recommendation_from_payload, _save_final_decisions
from meta_score.engine import MetaScoreEngine
from meta_score.validation_context import EnvironmentAdvisor
from recommendation.run_context import load_latest_context


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="AI 의사결정 엔진 대시보드", page_icon="🧠", layout="wide")
    _style(st)

    title_col, market_col = st.columns([5, 1])
    with title_col:
        st.markdown(
            '<div class="page-title"><h1>AI 의사결정 엔진 대시보드</h1>'
            '<p>하나의 추천 실행 ID를 기준으로 추천·비교·주문을 연결합니다.</p></div>',
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
        _render_generation_controls(st, profile, runtime)
        if context is None:
            st.info("저장된 추천 결과가 없습니다. 추천 생성 버튼을 먼저 실행하세요.")
            return

        name_map = build_name_map(conn, profile.code)
        recommendations = _enrich_recommendations(context.recommendations, name_map, profile.code)
        selected = _selected_recommendation(st, recommendations, profile.code)
        ticker = normalize_ticker(selected["ticker"], profile.code)
        payload = _safe_json(selected.get("payload_json"))
        validation = context.validations.get(ticker) or context.validations.get(str(selected["ticker"]))
        pattern = _selected_pattern(conn, payload)
        current = _current_bars(conn, profile.code, ticker, profile.price_source)
        historical = _pattern_bars(conn, pattern)

        _render_context_banner(st, context)
        _render_kpis(st, context, recommendations)

        step1, step2, step3 = st.columns([1.15, 3.15, 1.15], gap="medium")
        with step1:
            _step_title(st, 1, "추천 생성", "종목명과 주봉 순위점수를 표시합니다.")
            _recommendation_table(st, recommendations, selected)
        with step2:
            _step_title(st, 2, "추천 종목 비교", "현재 차트와 과거 급등 직전 패턴을 비교하고 필요할 때만 환경 조언을 확인합니다.")
            _comparison_panel(
                st, selected, current, historical, pattern, payload,
                profile.code, profile.db_path, context.run_id, validation,
            )
        with step3:
            _step_title(st, 3, "주문 관리", "환경 조언은 선택사항이며 주문 전에 참고할 수 있습니다.")
            _order_panel(st, selected, profile.code, validation, context)
    finally:
        conn.close()


def _render_generation_controls(st, profile, runtime) -> None:
    with st.expander("추천 생성 설정", expanded=False):
        c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1, 1.4])
        years = c1.number_input("과거 기간(년)", 1, 10, 2, key=f"wb5_{profile.code}_years")
        pool = c2.number_input("과거 패턴 수", 10, 1000, 100, 10, key=f"wb5_{profile.code}_pool")
        weekly = c3.number_input("최소 주봉", 0.0, 100.0, 85.0, 1.0, key=f"wb5_{profile.code}_weekly")
        sto = c4.number_input("STO 통과 기준", 0.0, 100.0, 85.0, 1.0, key=f"wb5_{profile.code}_sto")
        top_n = c5.number_input("추천 수", 1, 50, 20, key=f"wb5_{profile.code}_top")
        running = bool(runtime.get("running"))
        if c6.button("추천 생성 및 저장", type="primary", use_container_width=True, disabled=running):
            if start_job(
                profile.code, profile.db_path, top_n=int(top_n), weekly_pool_n=int(pool),
                candidate_years=int(years), use_recent_replay=True, use_weekly_filter=True,
                min_weekly_similarity=float(weekly), use_sto_filter=True,
                min_sto_similarity=float(sto),
            ):
                st.rerun()
        st.info("추천 순위는 주봉 유사도만 사용하고 STO는 기준 통과 여부만 확인합니다.")
        if running:
            st.progress(float(runtime.get("progress", 0.0) or 0.0), text=str(runtime.get("message", "추천 계산 중")))


def _render_context_banner(st, context) -> None:
    validated = len(context.validations)
    current_pending = len(context.current_orders)
    tone = "추천 연결" if validated == 0 else "환경 조언 포함"
    st.markdown(
        f'<div class="context-banner"><b>{tone}</b><span>run_id {context.run_id}</span>'
        f'<span>추천 {context.recommendation_count}개</span><span>환경 조언 {validated}개</span>'
        f'<span>현재 실행 주문 {current_pending}건</span></div>',
        unsafe_allow_html=True,
    )
    if context.other_pending_orders:
        st.warning(f"이전 추천 실행의 미처리 주문이 {context.other_pending_orders}건 있습니다. 현재 실행 주문과 분리해 표시합니다.")


def _render_kpis(st, context, recommendations) -> None:
    avg_weekly = sum(float(row["weekly_similarity"]) for row in recommendations) / len(recommendations)
    primary_cards = [
        ("오늘 추천", f"{len(recommendations)}개", "완료된 최신 실행"),
        ("평균 주봉 유사도", f"{avg_weekly:.1f}%", "추천 품질 기준"),
    ]
    secondary_cards = [
        ("현재 실행 주문", f"{len(context.current_orders)}건", "승인 전 요청"),
        ("환경 조언", f"{len(context.validations)}개", "선택 종목 확인"),
        ("미확인", f"{max(0, len(recommendations) - len(context.validations))}개", "조언 미실행"),
        ("최근 실행", str(context.finished_at or "없음")[:16], str(context.run_type or "-")),
    ]

    st.markdown('<div class="kpi-group kpi-group-primary">', unsafe_allow_html=True)
    cols = st.columns(2, gap="small")
    for col, (label, value, note) in zip(cols, primary_cards):
        col.markdown(
            f'<div class="kpi-card kpi-card-primary"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="kpi-group kpi-group-secondary">', unsafe_allow_html=True)
    cols = st.columns(4, gap="small")
    for col, (label, value, note) in zip(cols, secondary_cards):
        col.markdown(
            f'<div class="kpi-card kpi-card-secondary"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)


def _enrich_recommendations(rows, name_map, market):
    result = []
    for row in rows:
        item = dict(row)
        code = normalize_ticker(item.get("ticker"), market)
        item["ticker"] = code
        item["display_name"] = resolve_name(code, item.get("name"), name_map, market)
        item["symbol"] = display_symbol(item["display_name"], code, market)
        result.append(item)
    return result


def _selected_recommendation(st, recommendations, market):
    key = f"workbench_selected_{market}"
    tickers = [str(row["ticker"]) for row in recommendations]
    if st.session_state.get(key) not in tickers:
        st.session_state[key] = tickers[0]
    labels = {str(row["ticker"]): f"#{int(row['rank_no'])} {row['symbol']}" for row in recommendations}
    ticker = st.selectbox(
        "분석 종목 선택", tickers, index=tickers.index(st.session_state[key]),
        format_func=lambda value: labels[value], key=f"workbench_select_{market}",
    )
    st.session_state[key] = ticker
    return next(row for row in recommendations if str(row["ticker"]) == ticker)


def _recommendation_table(st, recommendations, selected) -> None:
    rows = []
    selected_ticker = str(selected["ticker"])
    for row in recommendations[:20]:
        rows.append({
            "": "▶" if str(row["ticker"]) == selected_ticker else "",
            "순위": int(row["rank_no"]),
            "종목": row["symbol"],
            "주봉": round(float(row["weekly_similarity"]), 1),
            "STO": round(float(row["sto_similarity"]), 1),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=650)


def _comparison_panel(st, selected, current, historical, pattern, payload, market, db_path, run_id, validation) -> None:
    st.markdown(
        f'<div class="selected-stock"><div><b>{selected["symbol"]}</b><small>{selected["ticker"]}</small></div>'
        f'<div><strong>주봉 {float(selected["weekly_similarity"]):.1f}%</strong>'
        f'<span>STO {float(selected["sto_similarity"]):.1f}% · PASS</span></div></div>',
        unsafe_allow_html=True,
    )
    if current.empty:
        st.warning("현재 가격 데이터가 부족합니다.")
        return

    chart_tab, compare_tab = st.tabs(["현재 종목 차트", "과거 패턴 비교"])
    with chart_tab:
        st.plotly_chart(build_trading_chart(current, selected["symbol"]), use_container_width=True, config=CHART_CONFIG)
    with compare_tab:
        if historical.empty or pattern is None:
            st.warning("비교 가능한 과거 패턴이 없습니다.")
        else:
            historical_label = display_symbol(pattern["name"] or pattern["ticker"], pattern["ticker"], market)
            st.plotly_chart(
                build_pattern_compare_chart(current, historical, selected["symbol"], historical_label),
                use_container_width=True, config=CHART_CONFIG,
            )

    metrics = st.columns(4, gap="small")
    values = [
        ("주봉 순위점수", f"{float(selected['weekly_similarity']):.1f}%"),
        ("STO 유사도", f"{float(selected['sto_similarity']):.1f}%"),
        ("STO 필터", "PASS"),
        ("과거 사례", f"{len(payload.get('replay_matches') or [])}건"),
    ]
    for col, (label, display) in zip(metrics, values):
        col.markdown(f'<div class="mini-card"><span>{label}</span><b>{display}</b></div>', unsafe_allow_html=True)

    st.markdown("#### 시장·업종 환경 조언")
    if validation is None:
        st.caption("선택 종목을 기준으로 전체 시장과 해당 업종 상태를 함께 확인합니다. 추천 순위는 바뀌지 않습니다.")
        if st.button(
            f"{selected['symbol']} 환경 조언 확인",
            key=f"validate_{run_id}_{selected['ticker']}",
            type="secondary",
            use_container_width=True,
        ):
            with st.spinner("전체 시장과 해당 업종 상태를 확인하고 있습니다..."):
                _run_selected_validation(db_path, run_id, selected, payload)
            st.success("선택 종목의 시장·업종 환경 조언을 저장했습니다.")
            st.rerun()
    else:
        _render_validation_summary(st, validation)


def _run_selected_validation(db_path, run_id, selected, payload) -> None:
    source = dict(payload)
    source["ticker"] = selected["ticker"]
    source["name"] = selected.get("display_name") or selected.get("name")
    recommendation = _recommendation_from_payload(source)
    environment = EnvironmentAdvisor().analyze(recommendation)
    results = MetaScoreEngine().score(
        [recommendation],
        validation_contexts={str(recommendation.ticker): environment},
    )
    _save_final_decisions(db_path, run_id, results)
    feedback = FeedbackEngine(db_path)
    feedback.record_validation_results(run_id, results)


def _render_validation_summary(st, validation) -> None:
    if validation is None:
        return
    row = dict(validation)
    final_score = float(row.get("final_score") or row.get("score") or 0.0)
    risk_score = float(row.get("risk_score") or 0.0)
    st.markdown(
        f'<div class="validation-summary"><b>환경 점수 {final_score:.1f}</b>'
        f'<span>위험도 {_risk_text(risk_score)} · 상태 {_status_text(final_score)}</span></div>',
        unsafe_allow_html=True,
    )


def _order_panel(st, selected, market, validation, context) -> None:
    st.markdown(
        f'<div class="order-card"><b>{selected["symbol"]}</b><span>{selected["ticker"]}</span></div>',
        unsafe_allow_html=True,
    )
    if validation is not None:
        st.caption("환경 조언이 저장된 종목입니다. 주문 전에 참고하세요.")
    st.page_link(
        "pages/9_Trading_Desk.py" if market == "kr" else "pages/12_US_Trading_Desk.py",
        label="주문 화면",
        icon="💳",
        use_container_width=True,
    )
    st.page_link(
        "pages/15_Scheduled_Orders.py",
        label="예약 주문",
        icon="🗓️",
        use_container_width=True,
    )
    st.markdown(
        f'<div class="order-count">현재 실행 주문 <b>{len(context.current_orders)}건</b></div>',
        unsafe_allow_html=True,
    )


def _selected_pattern(conn, payload):
    pattern_id = payload.get("selected_pattern_id")
    if not pattern_id:
        return None
    return conn.execute("SELECT * FROM surge_patterns WHERE pattern_id=?", (pattern_id,)).fetchone()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    if not table_name:
        return False
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _resolve_price_source(conn: sqlite3.Connection, configured_source: str) -> str | None:
    candidates = [configured_source, "ohlcv", "daily_prices", "price_daily", "prices"]
    for candidate in candidates:
        if candidate and _table_exists(conn, candidate):
            return candidate
    return None


def _current_bars(conn, market, ticker, source):
    resolved_source = _resolve_price_source(conn, str(source or ""))
    if resolved_source is None:
        return pd.DataFrame()
    rows = conn.execute(
        f'SELECT * FROM "{resolved_source}" WHERE ticker=? ORDER BY date DESC LIMIT 140',
        (ticker,),
    ).fetchall()
    frame = pd.DataFrame([dict(row) for row in rows])
    if not frame.empty and "date" in frame.columns:
        frame = frame.sort_values("date")
    return frame


def _pattern_bars(conn, pattern):
    if pattern is None or not _table_exists(conn, "surge_pattern_bars"):
        return pd.DataFrame()
    rows = conn.execute(
        "SELECT * FROM surge_pattern_bars WHERE pattern_id=? ORDER BY day_index",
        (pattern["pattern_id"],),
    ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _safe_json(value):
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _status_text(score):
    return "양호" if score >= 70 else "보통" if score >= 45 else "주의"


def _risk_text(score):
    return "낮음" if score >= 70 else "보통" if score >= 45 else "높음"


def _step_title(st, number, title, description):
    st.markdown(
        f'<div class="step-title"><span>{number}</span><div><b>{title}</b><small>{description}</small></div></div>',
        unsafe_allow_html=True,
    )


def _style(st):
    st.markdown("<style></style>", unsafe_allow_html=True)
