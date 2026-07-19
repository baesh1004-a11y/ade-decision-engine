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
    cards = [
        ("오늘 추천 종목", f"{len(recommendations)}개", "현재 완료 실행"),
        ("평균 주봉 유사도", f"{avg_weekly:.1f}%", "추천 순위 기준"),
        ("환경 조언", f"{len(context.validations)}개", "사용자 선택 실행"),
        ("미확인", f"{max(0, len(recommendations) - len(context.validations))}개", "조언 확인은 선택사항"),
        ("현재 실행 주문", f"{len(context.current_orders)}건", "승인 전 요청"),
        ("최근 실행", str(context.finished_at or "없음")[:16], str(context.run_type or "-")),
    ]
    cols = st.columns(6, gap="small")
    for col, (label, value, note) in zip(cols, cards):
        col.markdown(f'<div class="kpi-card"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>', unsafe_allow_html=True)


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
    try:
        feedback.register_meta_results(results)
    finally:
        feedback.close()


def _render_validation_summary(st, validation) -> None:
    decision = str(validation.get("decision"))
    label = {"FINAL BUY": "매수 검토", "BUY WATCH": "관찰", "HOLD": "보류", "PASS": "제외"}.get(decision, decision)
    st.markdown(f'<div class="validation-result"><span>시장·업종 환경 조언</span><strong>{label}</strong></div>', unsafe_allow_html=True)
    checks = [
        ("전체 시장 상태", _status_text(float(validation.get("market_score", 0)))),
        ("해당 업종 상태", _status_text(float(validation.get("sector_score", 0)))),
    ]
    cols = st.columns(2)
    for col, (title, value) in zip(cols, checks):
        col.markdown(f'<div class="validation-row"><b>{title}</b><span>{value}</span></div>', unsafe_allow_html=True)


def _order_panel(st, selected, market, validation, context) -> None:
    if validation is None:
        state = "주문 가능 · 환경 미확인"
        note = "시장·업종 환경 조언은 선택사항입니다."
    else:
        decision = str(validation.get("decision"))
        state = "주문 가능" if decision in {"FINAL BUY", "BUY WATCH"} else "환경 조언 주의"
        note = "시장·업종 환경 조언을 참고해 최종 판단하세요."
    st.markdown(f'<div class="order-highlight"><span>{selected["symbol"]}</span><strong>{state}</strong></div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.metric("현재 실행 주문", len(context.current_orders))
    c2.metric("환경 조언", "확인" if validation else "선택 안 함")
    target = "pages/9_Trading_Desk.py" if market == "kr" else "pages/12_US_Trading_Desk.py"
    st.page_link(target, label="주문관리 열기", icon="🛒", use_container_width=True)
    st.caption(f"{note} · 연결 run_id: {context.run_id}")


def _selected_pattern(conn, payload):
    matches = payload.get("replay_matches") or []
    if not matches:
        return None
    return conn.execute("SELECT * FROM surge_patterns WHERE pattern_id=?", (matches[0].get("event_id"),)).fetchone()


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
        f'<div class="step-header"><span>{number}</span><div><b>{title}</b><small>{description}</small></div></div>',
        unsafe_allow_html=True,
    )


def _style(st) -> None:
    st.markdown(
        """
        <style>
        :root{--navy:#09243d;--blue:#2778da;--ink:#152b42;--muted:#718397;--line:#dbe6ef;--panel:#fff}
        .stApp{background:linear-gradient(135deg,#f8fbfe,#eef4fa 55%,#fbfdff);color:var(--ink)}
        .block-container{max-width:2100px;padding:.55rem .8rem 2rem}
        [data-testid="stSidebar"]{background:linear-gradient(180deg,#08223a,#0c2c49)}
        [data-testid="stSidebar"] *{color:#edf7ff!important}
        .page-title h1{margin:0;font-size:28px}.page-title p{margin:2px 0 10px;color:var(--muted)}
        .context-banner{display:flex;gap:18px;align-items:center;padding:10px 14px;border:1px solid #cfe1f1;border-radius:12px;background:#eef7ff;margin:8px 0}.context-banner span{color:#557086;font-size:12px}.context-banner b{color:#1768bd}
        .kpi-card{min-height:100px;padding:15px;border-radius:15px;background:var(--panel);border:1px solid var(--line)}
        .kpi-card span,.kpi-card small{display:block;color:var(--muted)}.kpi-card strong{display:block;font-size:24px;margin:7px 0 4px}
        .step-header{display:flex;gap:10px;padding:13px 14px;margin-top:12px;border:1px solid var(--line);border-radius:14px 14px 0 0;background:linear-gradient(135deg,#fff,#f2f7fc)}
        .step-header>span{display:flex;align-items:center;justify-content:center;width:29px;height:29px;border-radius:8px;background:#2778da;color:white;font-weight:900}.step-header b{display:block;color:#165ea9;font-size:16px}.step-header small{display:block;color:var(--muted)}
        .selected-stock{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;margin:9px 0;border-radius:11px;background:#eef6ff;border:1px solid #d9e9f8}.selected-stock b{display:block;font-size:20px}.selected-stock small,.selected-stock span{display:block;color:var(--muted)}.selected-stock strong{display:block;color:#1976d2;text-align:right}
        .mini-card,.validation-result,.order-highlight{padding:11px 12px;border-radius:11px;background:white;border:1px solid var(--line);margin-bottom:8px}.mini-card span,.validation-result span{display:block;color:var(--muted);font-size:11px}.mini-card b,.validation-result strong{display:block;font-size:17px;margin-top:3px}
        .validation-row{display:flex;justify-content:space-between;padding:11px 12px;margin-top:7px;border-radius:10px;background:white;border:1px solid var(--line)}
        div[data-testid="stDataFrame"],div[data-testid="stPlotlyChart"]{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:white}
        </style>
        """,
        unsafe_allow_html=True,
    )
