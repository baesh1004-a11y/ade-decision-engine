from __future__ import annotations

import json
import sqlite3

import pandas as pd
import plotly.graph_objects as go

from markets.profiles import get_market_profile
from surge.multi_horizon import MULTI_PATTERN_VERSION, SURGE_CLASSES


CLASS_LABELS = {
    "FAST": "1~5일형",
    "QUICK": "6~10일형",
    "SWING": "11~15일형",
    "POSITION": "16~20일형",
}


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 추천 근거 비교", page_icon="📈", layout="wide")
    _style(st)

    market = st.segmented_control(
        "시장",
        options=["kr", "us"],
        default="kr",
        format_func=lambda value: "한국" if value == "kr" else "미국",
    )
    profile = get_market_profile(str(market or "kr"))

    st.markdown(
        f"""
        <section class="hero">
          <div>
            <div class="eyebrow">ADE · 추천 결과 설명 단계</div>
            <h1>{profile.name} 추천 근거 비교</h1>
            <p>추천 생성 당시 저장된 순위와 유사도를 그대로 사용해 현재 120일과 과거 급등직전 120일을 비교합니다.</p>
          </div>
          <div class="hero-badge">판정 변경 없음</div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.info("이 화면은 추천을 다시 계산하거나 새로운 점수·신뢰도·매수판정을 만들지 않습니다.")

    if not profile.db_path.exists():
        st.error(f"데이터베이스가 없습니다: {profile.db_path}")
        return

    conn = sqlite3.connect(str(profile.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "surge_patterns"):
            st.warning("급등직전 패턴 데이터가 없습니다.")
            return

        recommendations, parameters = _latest_recommendations(conn, profile.code)
        if not recommendations:
            st.info("먼저 추천 생성 메뉴에서 추천종목을 생성하세요.")
            return

        _render_run_info(st, parameters)
        selected = _select_recommendation(st, recommendations)
        payload = _safe_json(selected["payload_json"])
        matches = payload.get("replay_matches") or []
        enriched = _enrich_matches(conn, matches)
        if not enriched:
            st.warning("이 추천종목에 저장된 과거 매칭 사례가 없습니다.")
            return

        match, pattern = _select_pattern(st, enriched)
        current = _current_bars(conn, profile.code, str(selected["ticker"]), profile.price_source)
        historical = _historical_bars(conn, str(pattern["pattern_id"]))
        if current.empty or historical.empty:
            st.error("현재 또는 과거 비교 차트 데이터가 부족합니다.")
            return

        _render_saved_result(st, selected, match, pattern, len(enriched))

        left, right = st.columns([3, 1.2], gap="large")
        with left:
            st.markdown("### 현재 120일과 과거 급등직전 120일")
            st.plotly_chart(
                _comparison_chart(current, historical, selected, pattern),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        with right:
            _render_pattern_source(st, pattern)

        c1, c2 = st.columns([1.5, 1], gap="large")
        with c1:
            _render_match_table(st, enriched, pattern)
        with c2:
            _render_return_path(st, pattern)

        st.markdown("### 추천 생성 당시 저장된 근거")
        stored_reasons = payload.get("reasons") or []
        if stored_reasons:
            for reason in stored_reasons:
                st.markdown(f'<div class="reason-box">{reason}</div>', unsafe_allow_html=True)
        else:
            st.caption("저장된 설명 문구가 없습니다.")

        st.caption("추천 순위와 유사도는 추천 생성 단계의 저장값입니다. 이 화면에서는 값을 재계산하거나 변경하지 않습니다.")
    finally:
        conn.close()


def _render_run_info(st, parameters: dict[str, object]) -> None:
    years = parameters.get("candidate_years", "-")
    pool = parameters.get("weekly_pool_n", "-")
    weekly = parameters.get("min_weekly_similarity", "-")
    sto = parameters.get("min_sto_similarity", "-")
    cols = st.columns(4)
    cols[0].metric("과거 패턴 기간", f"{years}년" if years != "-" else "-")
    cols[1].metric("비교 패턴 수", pool)
    cols[2].metric("추천 당시 주봉 기준", f"{weekly}%" if weekly != "-" else "-")
    cols[3].metric("추천 당시 STO 기준", f"{sto}%" if sto != "-" else "-")


def _select_recommendation(st, recommendations: list[sqlite3.Row]) -> sqlite3.Row:
    st.markdown("### 1. 추천종목 선택")
    options = list(range(len(recommendations)))
    selected_index = st.selectbox(
        "추천종목",
        options,
        format_func=lambda i: (
            f"#{int(recommendations[i]['rank_no'])} "
            f"{recommendations[i]['name'] or recommendations[i]['ticker']} "
            f"· 최종 유사도 {float(recommendations[i]['final_similarity']):.1f}%"
        ),
        label_visibility="collapsed",
    )
    return recommendations[int(selected_index)]


def _select_pattern(st, enriched: list[tuple[dict[str, object], sqlite3.Row]]):
    st.markdown("### 2. 저장된 과거 매칭 사례 선택")
    options = list(range(len(enriched)))
    selected_index = st.selectbox(
        "과거 매칭 사례",
        options,
        format_func=lambda i: (
            f"{enriched[i][1]['name'] or enriched[i][1]['ticker']} "
            f"· {CLASS_LABELS.get(str(enriched[i][1]['surge_class']), enriched[i][1]['surge_class'])} "
            f"· 주봉 {float(enriched[i][0].get('weekly_similarity', 0)):.1f}% "
            f"· STO {float(enriched[i][0].get('sto_similarity', 0)):.1f}%"
        ),
        label_visibility="collapsed",
    )
    return enriched[int(selected_index)]


def _render_saved_result(st, selected, match, pattern, sample_count: int) -> None:
    st.markdown("### 추천 생성 결과")
    cols = st.columns(5)
    cols[0].metric("추천 순위", f"#{int(selected['rank_no'])}")
    cols[1].metric("최종 유사도", f"{float(selected['final_similarity']):.1f}%")
    cols[2].metric("주봉 유사도", f"{float(match.get('weekly_similarity', 0)):.1f}%")
    cols[3].metric("STO 유사도", f"{float(match.get('sto_similarity', 0)):.1f}%")
    cols[4].metric("저장된 사례", f"{sample_count}건")
    st.caption(
        f"대표 과거 사례: {pattern['name'] or pattern['ticker']} · "
        f"30% 최초 도달 {int(pattern['target_hit_day'])}거래일 · "
        f"최대상승 +{float(pattern['surge_return_pct']):.1f}%"
    )


def _render_pattern_source(st, pattern) -> None:
    st.markdown("### 과거 사례 정보")
    rows = [
        ("과거 종목", f"{pattern['name'] or pattern['ticker']} ({pattern['ticker']})"),
        ("패턴 기간", f"{pattern['pattern_start_date']} ~ {pattern['pattern_end_date']}"),
        ("급등 시작", pattern["surge_start_date"]),
        ("급등 유형", CLASS_LABELS.get(str(pattern["surge_class"]), pattern["surge_class"])),
        ("30% 도달", f"{int(pattern['target_hit_day'])}거래일"),
        ("최대상승", f"+{float(pattern['surge_return_pct']):.2f}%"),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["항목", "값"]), use_container_width=True, hide_index=True)


def _render_match_table(st, enriched, selected_pattern) -> None:
    st.markdown("### 저장된 상위 매칭 사례")
    rows = []
    for item, pattern in enriched:
        rows.append(
            {
                "선택": "●" if pattern["pattern_id"] == selected_pattern["pattern_id"] else "",
                "과거 종목": pattern["name"] or pattern["ticker"],
                "유형": CLASS_LABELS.get(str(pattern["surge_class"]), pattern["surge_class"]),
                "주봉 유사도": round(float(item.get("weekly_similarity", 0)), 1),
                "STO 유사도": round(float(item.get("sto_similarity", 0)), 1),
                "30% 도달일": int(pattern["target_hit_day"]),
                "최대상승": round(float(pattern["surge_return_pct"]), 1),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_return_path(st, pattern) -> None:
    st.markdown("### 과거 상승 경로")
    frame = pd.DataFrame(
        {
            "기간": ["5일", "10일", "15일", "20일"],
            "최고상승률": [pattern["return_5d"], pattern["return_10d"], pattern["return_15d"], pattern["return_20d"]],
        }
    )
    figure = go.Figure(go.Bar(x=frame["기간"], y=frame["최고상승률"], text=frame["최고상승률"], textposition="outside"))
    figure.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis_title="최고상승률(%)",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.70)",
    )
    st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})


def _comparison_chart(current: pd.DataFrame, historical: pd.DataFrame, selected, pattern) -> go.Figure:
    current = current.reset_index(drop=True)
    historical = historical.reset_index(drop=True)
    current_base = float(current.iloc[0]["Close"]) or 1.0
    historical_base = float(historical.iloc[0]["close"]) or 1.0
    current_values = (current["Close"].astype(float) / current_base - 1.0) * 100.0
    historical_values = (historical["close"].astype(float) / historical_base - 1.0) * 100.0
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=list(range(len(current_values))), y=current_values, mode="lines", name=f"현재 {selected['ticker']}", line=dict(width=3)))
    figure.add_trace(go.Scatter(x=list(range(len(historical_values))), y=historical_values, mode="lines", name=f"과거 {pattern['ticker']}", line=dict(width=2, dash="dot")))
    figure.add_hline(y=0, line_width=1, line_dash="dash", line_color="rgba(70,100,130,.25)")
    figure.update_layout(
        height=560,
        margin=dict(l=18, r=18, t=40, b=20),
        xaxis_title="120거래일 진행",
        yaxis_title="시작일 대비 등락률(%)",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.74)",
    )
    return figure


def _latest_recommendations(conn: sqlite3.Connection, market: str) -> tuple[list[sqlite3.Row], dict[str, object]]:
    if not _table_exists(conn, "daily_recommendations") or not _table_exists(conn, "recommendation_runs"):
        return [], {}
    run = conn.execute(
        """
        SELECT run_id, parameters_json
        FROM recommendation_runs
        WHERE status='COMPLETED'
          AND EXISTS(
              SELECT 1 FROM daily_recommendations d
              WHERE d.run_id=recommendation_runs.run_id AND d.market=?
          )
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (market,),
    ).fetchone()
    if run is None:
        return [], {}
    rows = conn.execute(
        """
        SELECT rank_no, ticker, name, decision, final_similarity,
               weekly_similarity, sto_similarity, payload_json
        FROM daily_recommendations
        WHERE run_id=? AND market=?
        ORDER BY rank_no
        """,
        (run["run_id"], market),
    ).fetchall()
    return rows, _safe_json(run["parameters_json"])


def _enrich_matches(conn: sqlite3.Connection, matches):
    enriched = []
    for item in matches:
        pattern = conn.execute(
            "SELECT * FROM surge_patterns WHERE pattern_id=? AND pattern_version=?",
            (item.get("event_id"), MULTI_PATTERN_VERSION),
        ).fetchone()
        if pattern is not None:
            enriched.append((item, pattern))
    return enriched


def _current_bars(conn: sqlite3.Connection, market: str, ticker: str, source: str) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT trade_date AS Date, open AS Open, high AS High, low AS Low,
               close AS Close, volume AS Volume
        FROM price_bars
        WHERE market=? AND ticker=? AND source=?
        ORDER BY trade_date DESC
        LIMIT 120
        """,
        (market, ticker, source),
    ).fetchall()
    return pd.DataFrame([dict(row) for row in reversed(rows)])


def _historical_bars(conn: sqlite3.Connection, pattern_id: str) -> pd.DataFrame:
    rows = conn.execute(
        "SELECT * FROM surge_pattern_bars WHERE pattern_id=? ORDER BY day_index",
        (pattern_id,),
    ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _safe_json(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value)) if value else {}
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _style(st) -> None:
    st.markdown(
        """
        <style>
        :root{--ink:#14283d;--muted:#6d8092;--line:rgba(72,119,160,.16)}
        .stApp{background:radial-gradient(circle at 10% 0%,rgba(112,184,255,.20),transparent 28%),linear-gradient(135deg,#f8fbfe,#eef5fb 52%,#fbfdff);color:var(--ink)}
        .block-container{max-width:1650px;padding-top:1rem;padding-bottom:3rem}
        .hero{display:flex;align-items:center;justify-content:space-between;padding:28px 32px;border-radius:26px;background:linear-gradient(135deg,rgba(255,255,255,.95),rgba(238,247,255,.86));border:1px solid var(--line);box-shadow:0 20px 58px rgba(45,89,127,.11);margin-bottom:18px}
        .hero h1{font-size:36px;letter-spacing:-.045em;margin:4px 0 8px}.hero p{margin:0;color:var(--muted)}
        .eyebrow{font-size:12px;letter-spacing:.15em;font-weight:850;color:#2b75b8}.hero-badge{padding:12px 18px;border-radius:999px;background:#eaf4ff;color:#246aa8;font-weight:850}
        .reason-box{padding:14px 16px;border-radius:16px;background:rgba(255,255,255,.78);border:1px solid var(--line);margin-bottom:8px;color:#28445d}
        div[data-testid="stMetric"],div[data-testid="stDataFrame"]{background:rgba(255,255,255,.78);border:1px solid var(--line);border-radius:18px}
        @media(max-width:900px){.block-container{padding:.7rem}.hero{display:block;padding:20px}.hero h1{font-size:28px}.hero-badge{display:none}}
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    run()
