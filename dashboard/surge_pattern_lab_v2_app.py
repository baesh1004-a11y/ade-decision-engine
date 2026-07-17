from __future__ import annotations

import json
import sqlite3

import pandas as pd

from dashboard.charts import CHART_CONFIG, build_pattern_compare_chart, build_trading_chart
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, display_symbol, normalize_ticker, resolve_name
from recommendation.run_context import load_latest_context


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 추천 근거 비교", page_icon="📈", layout="wide")
    _style(st)
    market = st.segmented_control(
        "시장", options=["kr", "us"], default="kr",
        format_func=lambda value: "한국" if value == "kr" else "미국",
    )
    profile = get_market_profile(str(market or "kr"))
    st.markdown(
        f'<section class="hero"><div><div class="eyebrow">ADE · 추천 결과 설명 단계</div>'
        f'<h1>{profile.name} 추천 근거 비교</h1><p>통합 워크벤치와 동일한 추천 실행과 동일한 차트 기준을 사용합니다.</p></div>'
        f'<div class="hero-badge">판정 변경 없음</div></section>',
        unsafe_allow_html=True,
    )
    if not profile.db_path.exists():
        st.error(f"데이터베이스가 없습니다: {profile.db_path}")
        return

    conn = sqlite3.connect(str(profile.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        context = load_latest_context(conn, profile.code, 50)
        if context is None or not context.recommendations:
            st.info("먼저 추천 생성 메뉴에서 추천종목을 생성하세요.")
            return
        name_map = build_name_map(conn, profile.code)
        recommendations = []
        for row in context.recommendations:
            item = dict(row)
            code = normalize_ticker(item.get("ticker"), profile.code)
            name = resolve_name(code, item.get("name"), name_map, profile.code)
            item["ticker"] = code
            item["name"] = name
            item["symbol"] = display_symbol(name, code, profile.code)
            recommendations.append(item)

        st.caption(
            f"연결 run_id: {context.run_id} · 완료 시각: {context.finished_at or '-'} · "
            f"추천 {context.recommendation_count}개"
        )
        selected_index = st.selectbox(
            "추천종목",
            list(range(len(recommendations))),
            format_func=lambda i: (
                f"#{int(recommendations[i]['rank_no'])} {recommendations[i]['symbol']} · "
                f"주봉 {float(recommendations[i]['weekly_similarity']):.1f}% · "
                f"STO {float(recommendations[i]['sto_similarity']):.1f}%"
            ),
        )
        selected = recommendations[int(selected_index)]
        payload = _safe_json(selected.get("payload_json"))
        matches = payload.get("replay_matches") or []
        if not matches:
            st.warning("저장된 과거 매칭 사례가 없습니다.")
            return

        enriched = []
        for match in matches:
            pattern = conn.execute(
                "SELECT * FROM surge_patterns WHERE pattern_id=?", (match.get("event_id"),)
            ).fetchone()
            if pattern is not None:
                enriched.append((match, pattern))
        if not enriched:
            st.warning("과거 패턴 원본을 찾을 수 없습니다.")
            return

        pattern_index = st.selectbox(
            "과거 매칭 사례",
            list(range(len(enriched))),
            format_func=lambda i: (
                f"{display_symbol(enriched[i][1]['name'] or enriched[i][1]['ticker'], enriched[i][1]['ticker'], profile.code)} · "
                f"주봉 {float(enriched[i][0].get('weekly_similarity', 0)):.1f}% · "
                f"STO {float(enriched[i][0].get('sto_similarity', 0)):.1f}%"
            ),
        )
        match, pattern = enriched[int(pattern_index)]
        current = _current_bars(conn, profile.code, selected["ticker"], profile.price_source)
        historical = _historical_bars(conn, str(pattern["pattern_id"]))
        if current.empty or historical.empty:
            st.error("현재 또는 과거 비교 차트 데이터가 부족합니다.")
            return

        metrics = st.columns(4)
        metrics[0].metric("추천 순위", f"#{int(selected['rank_no'])}")
        metrics[1].metric("주봉 순위점수", f"{float(selected['weekly_similarity']):.1f}%")
        metrics[2].metric("STO 유사도", f"{float(selected['sto_similarity']):.1f}%")
        metrics[3].metric("STO 필터", "PASS")

        chart_tab, compare_tab = st.tabs(["현재 종목 차트", "과거 패턴 비교"])
        with chart_tab:
            st.plotly_chart(build_trading_chart(current, selected["symbol"]), use_container_width=True, config=CHART_CONFIG)
            st.caption("화면 STO는 일반 Stochastic(14,3) 참고 차트이며 추천 STO 구조점수와는 별도입니다.")
        with compare_tab:
            historical_label = display_symbol(pattern["name"] or pattern["ticker"], pattern["ticker"], profile.code)
            st.plotly_chart(
                build_pattern_compare_chart(current, historical, selected["symbol"], historical_label),
                use_container_width=True,
                config=CHART_CONFIG,
            )

        left, right = st.columns([1.5, 1], gap="large")
        with left:
            st.markdown("### 저장된 상위 매칭 사례")
            rows = []
            for item, row in enriched:
                rows.append({
                    "과거 종목": display_symbol(row["name"] or row["ticker"], row["ticker"], profile.code),
                    "유형": row["surge_class"],
                    "주봉 유사도": round(float(item.get("weekly_similarity", 0)), 1),
                    "STO 유사도": round(float(item.get("sto_similarity", 0)), 1),
                    "30% 도달일": int(row["target_hit_day"]),
                    "최대상승": round(float(row["surge_return_pct"]), 1),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        with right:
            st.markdown("### 추천 생성 당시 저장된 근거")
            for reason in payload.get("reasons") or []:
                st.markdown(f'<div class="reason-box">{reason}</div>', unsafe_allow_html=True)
    finally:
        conn.close()


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


def _historical_bars(conn, pattern_id):
    rows = conn.execute(
        "SELECT * FROM surge_pattern_bars WHERE pattern_id=? ORDER BY day_index", (pattern_id,)
    ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _safe_json(value):
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _style(st) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#f9fbff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1800px;padding-top:1rem}
        .hero{display:flex;justify-content:space-between;align-items:center;padding:24px 28px;border:1px solid rgba(76,145,207,.23);border-radius:24px;background:rgba(255,255,255,.84);margin-bottom:14px}
        .hero h1{margin:3px 0}.hero p{margin:5px 0;color:#647b92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}.hero-badge{padding:11px 15px;border-radius:999px;background:#eaf4ff;color:#286ba6;font-weight:800}
        .reason-box{padding:11px 12px;border-radius:10px;background:white;border:1px solid #dbe6ef;margin-bottom:8px}
        div[data-testid="stDataFrame"],div[data-testid="stPlotlyChart"]{border:1px solid #dbe6ef;border-radius:10px;overflow:hidden;background:white}
        </style>
        """,
        unsafe_allow_html=True,
    )
