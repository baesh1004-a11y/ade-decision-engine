from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from dashboard import recommendation_workbench_v2_app as base
from dashboard.charts import CHART_CONFIG, build_pattern_compare_chart, build_trading_chart
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, normalize_ticker
from recommendation.run_context import load_latest_context


def run() -> None:
    st.set_page_config(page_title="ADE 추천 근거 비교", page_icon="🔍", layout="wide")
    base._style(st)

    title_col, market_col = st.columns([5, 1])
    with title_col:
        st.markdown(
            '<div class="page-title"><h1>추천 근거 비교</h1>'
            '<p>현재 종목과 가장 유사한 과거 급등 직전 사례를 근거별로 비교합니다.</p></div>',
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
        if context is None:
            st.info("저장된 추천 결과가 없습니다.")
            return

        recommendations = base._enrich_recommendations(
            context.recommendations, build_name_map(conn, profile.code), profile.code
        )
        selected = _selected_from_controller(recommendations, profile.code)
        ticker = normalize_ticker(selected["ticker"], profile.code)
        payload = base._safe_json(selected.get("payload_json"))
        pattern = base._selected_pattern(conn, payload)
        current = base._current_bars(conn, profile.code, ticker, profile.price_source)
        historical = base._pattern_bars(conn, pattern)

        _top_metrics(selected, payload)
        left, center, right = st.columns([1.05, 2.5, 1.1], gap="medium")
        with left:
            st.markdown("### 추천 종목")
            _recommendation_controller(recommendations, selected, profile.code)
        with center:
            _comparison(selected, current, historical, pattern, payload, profile.code)
        with right:
            _interpretation(selected, payload, pattern)
    finally:
        conn.close()


def _selected_from_controller(recommendations, market: str):
    key = f"evidence_selected_{market}"
    tickers = [str(row["ticker"]) for row in recommendations]
    if st.session_state.get(key) not in tickers:
        st.session_state[key] = tickers[0]
    return next(row for row in recommendations if str(row["ticker"]) == st.session_state[key])


def _recommendation_controller(recommendations, selected, market: str) -> None:
    rows = [{
        "순위": int(r["rank_no"]),
        "종목": r["symbol"],
        "주봉": round(float(r["weekly_similarity"]), 1),
        "ticker": str(r["ticker"]),
    } for r in recommendations[:20]]
    frame = pd.DataFrame(rows)
    event = st.dataframe(
        frame[["순위", "종목", "주봉"]], use_container_width=True, hide_index=True,
        height=690, on_select="rerun", selection_mode="single-row",
        key=f"evidence_controller_{market}",
    )
    selected_rows = getattr(getattr(event, "selection", None), "rows", [])
    if selected_rows:
        ticker = frame.iloc[int(selected_rows[0])]["ticker"]
        if ticker != st.session_state.get(f"evidence_selected_{market}"):
            st.session_state[f"evidence_selected_{market}"] = ticker
            st.rerun()
    st.caption(f"현재 선택: {selected['symbol']}")


def _top_metrics(selected, payload) -> None:
    matches = payload.get("replay_matches") or []
    cols = st.columns(4)
    cols[0].metric("선택 종목", selected["symbol"])
    cols[1].metric("주봉 유사도", f"{float(selected['weekly_similarity']):.1f}%")
    cols[2].metric("STO 유사도", f"{float(selected['sto_similarity']):.1f}%")
    cols[3].metric("비교 사례", f"{len(matches)}건")


def _comparison(selected, current, historical, pattern, payload, market: str) -> None:
    st.markdown(f"### {selected['symbol']} 패턴 비교")
    if current.empty:
        st.warning("현재 가격 데이터가 부족합니다.")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 현재 120일 패턴")
        st.plotly_chart(build_trading_chart(current, selected["symbol"]), use_container_width=True, config=CHART_CONFIG)
    with c2:
        st.markdown("#### 가장 유사한 과거 사례")
        if historical.empty or pattern is None:
            st.warning("비교 가능한 과거 패턴이 없습니다.")
        else:
            label = str(pattern["name"] or pattern["ticker"])
            st.plotly_chart(
                build_pattern_compare_chart(current, historical, selected["symbol"], label),
                use_container_width=True, config=CHART_CONFIG,
            )

    weekly = float(selected["weekly_similarity"])
    sto = float(selected["sto_similarity"])
    volume = _payload_score(payload, ["volume_similarity", "volume_score"], default=(weekly + sto) / 2)
    total = weekly
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("가격 흐름", f"{weekly:.1f}%")
    m2.metric("거래량 흐름", f"{volume:.1f}%")
    m3.metric("STO 흐름", f"{sto:.1f}%")
    m4.metric("종합 유사도", f"{total:.1f}%")

    st.markdown("#### 구간별 유사성")
    segments = [
        ("초반 바닥 형성", _payload_score(payload, ["early_similarity"], weekly)),
        ("중반 거래량 변화", _payload_score(payload, ["middle_similarity"], volume)),
        ("후반 상승 전환", _payload_score(payload, ["late_similarity"], (weekly + sto) / 2)),
    ]
    for label, value in segments:
        st.write(f"{label} · {value:.1f}%")
        st.progress(max(0.0, min(1.0, value / 100.0)))


def _interpretation(selected, payload, pattern) -> None:
    st.markdown("### 근거 해석")
    weekly = float(selected["weekly_similarity"])
    sto = float(selected["sto_similarity"])
    if weekly >= 90:
        conclusion = "과거 급등 직전 주봉 구조와 매우 높은 유사성을 보입니다."
    elif weekly >= 85:
        conclusion = "과거 급등 직전 주봉 구조와 높은 유사성을 보입니다."
    else:
        conclusion = "유사 패턴이 있으나 추가 확인이 필요합니다."
    st.info(conclusion)

    reasons = [
        f"주봉 순위점수 {weekly:.1f}%",
        f"STO 유사도 {sto:.1f}% · 기준 통과",
        f"과거 비교 사례 {len(payload.get('replay_matches') or [])}건",
    ]
    if pattern is not None:
        reasons.append(f"최우선 비교 패턴: {pattern['name'] or pattern['ticker']}")
    for reason in reasons:
        st.markdown(f"- {reason}")

    after20 = _payload_value(payload, ["return_20d", "after_20d_return"])
    after60 = _payload_value(payload, ["return_60d", "after_60d_return"])
    st.divider()
    st.markdown("#### 과거 사례 이후 결과")
    c1, c2 = st.columns(2)
    c1.metric("20일 후", _format_return(after20))
    c2.metric("60일 후", _format_return(after60))
    st.caption("과거 유사 사례는 참고 근거이며 동일한 수익률을 보장하지 않습니다.")
    st.page_link("pages/14_Recommendation_Workbench.py", label="투자 워크벤치에서 검토", icon="📊", use_container_width=True)


def _payload_score(payload, keys, default: float) -> float:
    value = _payload_value(payload, keys)
    try:
        number = float(value)
        return number * 100 if 0 <= number <= 1 else number
    except (TypeError, ValueError):
        return float(default)


def _payload_value(payload, keys):
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    for match in payload.get("replay_matches") or []:
        for key in keys:
            if key in match and match[key] is not None:
                return match[key]
    return None


def _format_return(value) -> str:
    if value is None:
        return "데이터 없음"
    try:
        number = float(value)
        number = number * 100 if -1 <= number <= 1 else number
        return f"{number:+.1f}%"
    except (TypeError, ValueError):
        return str(value)
