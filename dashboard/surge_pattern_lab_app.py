from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from markets.profiles import get_market_profile
from sto.structure_similarity import STOStructureSimilarityEngine


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE Surge Pattern Lab", page_icon="📈", layout="wide")
    st.markdown(
        """
        <style>
        .stApp{background:radial-gradient(circle at 12% 0%,rgba(125,190,255,.20),transparent 27%),linear-gradient(135deg,#f7fbff,#eef5fb 52%,#f9fcff);color:#14263a}
        .block-container{max-width:1580px;padding-top:1.05rem;padding-bottom:3rem}
        .hero{padding:30px 34px;border-radius:28px;background:linear-gradient(135deg,rgba(255,255,255,.95),rgba(240,248,255,.88));border:1px solid rgba(77,125,168,.18);box-shadow:0 22px 62px rgba(42,88,130,.12);margin-bottom:20px}
        .hero h1{margin:5px 0 7px;font-size:36px;letter-spacing:-.045em}.hero p{margin:0;color:#6d8194}.eyebrow{font-size:12px;letter-spacing:.16em;font-weight:850;color:#2f78ba}
        div[data-testid="stMetric"]{background:rgba(255,255,255,.80);border:1px solid rgba(77,125,168,.18);padding:15px 17px;border-radius:17px}
        div[data-testid="stDataFrame"]{border-radius:18px;overflow:hidden;border:1px solid rgba(77,125,168,.18)}
        </style>
        <div class="hero">
          <div class="eyebrow">ADE · PRE-SURGE 120D PATTERN LAB</div>
          <h1>급등직전 패턴 비교</h1>
          <p>추천종목의 최근 120거래일과 과거 5거래일 30% 급등 직전 120거래일을 직접 비교합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    market = st.segmented_control("시장", options=["kr", "us"], default="kr", format_func=lambda value: "한국장" if value == "kr" else "미국장")
    profile = get_market_profile(str(market or "kr"))
    if not profile.db_path.exists():
        st.error(f"{profile.db_path}가 없습니다.")
        return

    conn = sqlite3.connect(str(profile.db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "surge_patterns"):
            st.warning("급등직전 패턴 DB가 없습니다.")
            st.code(f"python run_build_surge_patterns.py --market {profile.code} --full", language="bash")
            return

        summary = conn.execute(
            """
            SELECT COUNT(*) AS patterns, COUNT(DISTINCT ticker) AS symbols,
                   AVG(surge_return_5d) AS avg_return, MAX(surge_return_5d) AS max_return
            FROM surge_patterns WHERE market=?
            """,
            (profile.code,),
        ).fetchone()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("급등직전 패턴", f"{int(summary['patterns'] or 0):,}")
        m2.metric("패턴 보유 종목", f"{int(summary['symbols'] or 0):,}")
        m3.metric("평균 5일 최고상승", f"{float(summary['avg_return'] or 0):.1f}%")
        m4.metric("최대 5일 상승", f"{float(summary['max_return'] or 0):.1f}%")

        recommendations = _latest_recommendations(conn, profile.code)
        if not recommendations:
            st.info("완료된 추천 결과가 없습니다. Daily Recommendation에서 추천을 먼저 생성하세요.")
            st.markdown("### 급등직전 패턴 라이브러리")
            st.dataframe(pd.DataFrame(_pattern_rows(conn, profile.code, 200)), use_container_width=True, hide_index=True)
            return

        labels = [
            f"#{row['rank_no']} {row['name'] or row['ticker']} ({row['ticker']}) · 유사도 {float(row['final_similarity']):.1f}%"
            for row in recommendations
        ]
        selected_index = st.selectbox("추천종목", range(len(recommendations)), format_func=lambda idx: labels[idx])
        selected = recommendations[selected_index]
        payload = json.loads(str(selected["payload_json"]))
        matches = payload.get("replay_matches") or []
        if not matches:
            st.warning("이 추천에는 저장된 급등직전 매칭 패턴이 없습니다.")
            return

        match_labels = [
            f"{item.get('ticker')} · 급등 {item.get('event_date')} · 차트 {float(item.get('weekly_similarity', 0)):.1f}% · STO {float(item.get('sto_similarity', 0)):.1f}% · +{float(item.get('max_return') or 0):.1f}%"
            for item in matches
        ]
        match_index = st.selectbox("비교할 과거 급등직전 패턴", range(len(matches)), format_func=lambda idx: match_labels[idx])
        match = matches[match_index]
        pattern = conn.execute("SELECT * FROM surge_patterns WHERE pattern_id=?", (match["event_id"],)).fetchone()
        if pattern is None:
            st.error("선택한 패턴을 찾을 수 없습니다.")
            return

        current = _current_bars(conn, profile.code, str(selected["ticker"]), profile.price_source)
        historical = pd.DataFrame(
            [dict(row) for row in conn.execute(
                "SELECT * FROM surge_pattern_bars WHERE pattern_id=? ORDER BY day_index",
                (pattern["pattern_id"],),
            ).fetchall()]
        )
        if current.empty or historical.empty:
            st.error("비교 차트 데이터가 부족합니다.")
            return

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("차트 유사도", f"{float(match.get('weekly_similarity', 0)):.2f}%")
        c2.metric("STO 3계층 유사도", f"{float(match.get('sto_similarity', 0)):.2f}%")
        c3.metric("과거 5일 최고상승", f"+{float(pattern['surge_return_5d']):.2f}%")
        c4.metric("대금 폭발→급등", f"{int(pattern['observation_days'])}거래일")

        st.markdown("### 최근 120일 vs 과거 급등직전 120일")
        st.plotly_chart(_comparison_chart(current, historical, selected, pattern), use_container_width=True)

        current_sto = STOStructureSimilarityEngine().extract(current)
        historical_sto = json.loads(str(pattern["sto_json"]))
        st.markdown("### STO 3계층 비교")
        s1, s2, s3 = st.columns(3)
        s1.metric("단기 STO", f"현재 {current_sto.short:.1f}", delta=f"과거 {float(historical_sto['short']):.1f}")
        s2.metric("중기 STO", f"현재 {current_sto.middle:.1f}", delta=f"과거 {float(historical_sto['middle']):.1f}")
        s3.metric("장기 STO", f"현재 {current_sto.long:.1f}", delta=f"과거 {float(historical_sto['long']):.1f}")

        st.markdown("### 패턴 출처")
        info = pd.DataFrame([
            {
                "원본 종목": f"{pattern['name'] or pattern['ticker']} ({pattern['ticker']})",
                "거래대금 폭발일": pattern["money_event_date"],
                "거래대금 배수": pattern["money_ratio_120d"],
                "패턴 시작": pattern["pattern_start_date"],
                "패턴 종료": pattern["pattern_end_date"],
                "급등 시작": pattern["surge_start_date"],
                "급등 최고점": pattern["surge_peak_date"],
                "5일 최고상승률": pattern["surge_return_5d"],
            }
        ])
        st.dataframe(info, use_container_width=True, hide_index=True)

        with st.expander("급등직전 패턴 라이브러리 전체 보기"):
            st.dataframe(pd.DataFrame(_pattern_rows(conn, profile.code, 500)), use_container_width=True, hide_index=True)
    finally:
        conn.close()


def _comparison_chart(current: pd.DataFrame, historical: pd.DataFrame, selected: sqlite3.Row, pattern: sqlite3.Row) -> go.Figure:
    current = current.copy().reset_index(drop=True)
    historical = historical.copy().reset_index(drop=True)
    current_base = float(current.iloc[0]["Close"]) or 1.0
    current["normalized_close"] = (current["Close"].astype(float) / current_base - 1.0) * 100.0
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=list(range(len(current))), y=current["normalized_close"], mode="lines", name=f"현재 {selected['ticker']}"))
    figure.add_trace(go.Scatter(x=list(range(len(historical))), y=historical["normalized_close"], mode="lines", name=f"과거 {pattern['ticker']} 급등직전"))
    figure.update_layout(
        height=520,
        margin=dict(l=20, r=20, t=35, b=20),
        xaxis_title="120거래일 진행",
        yaxis_title="시작일 대비 등락률(%)",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.72)",
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="rgba(90,130,170,.12)")
    return figure


def _latest_recommendations(conn: sqlite3.Connection, market: str) -> list[sqlite3.Row]:
    if not _table_exists(conn, "daily_recommendations"):
        return []
    run = conn.execute(
        """
        SELECT r.run_id FROM recommendation_runs r
        WHERE r.status='COMPLETED'
          AND EXISTS(SELECT 1 FROM daily_recommendations d WHERE d.run_id=r.run_id AND d.market=?)
        ORDER BY r.started_at DESC LIMIT 1
        """,
        (market,),
    ).fetchone()
    if run is None:
        return []
    return conn.execute(
        """
        SELECT rank_no, ticker, name, decision, final_similarity,
               weekly_similarity, sto_similarity, payload_json
        FROM daily_recommendations WHERE run_id=? AND market=? ORDER BY rank_no
        """,
        (run["run_id"], market),
    ).fetchall()


def _current_bars(conn: sqlite3.Connection, market: str, ticker: str, source: str) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT trade_date AS Date, open AS Open, high AS High, low AS Low,
               close AS Close, volume AS Volume
        FROM price_bars WHERE market=? AND ticker=? AND source=?
        ORDER BY trade_date DESC LIMIT 120
        """,
        (market, ticker, source),
    ).fetchall()
    return pd.DataFrame([dict(row) for row in reversed(rows)])


def _pattern_rows(conn: sqlite3.Connection, market: str, limit: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT ticker, name, money_event_date, money_ratio_120d,
               pattern_start_date, pattern_end_date, surge_start_date,
               surge_peak_date, surge_return_5d, observation_days
        FROM surge_patterns WHERE market=?
        ORDER BY surge_return_5d DESC LIMIT ?
        """,
        (market, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


if __name__ == "__main__":
    run()
