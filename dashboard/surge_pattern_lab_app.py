from __future__ import annotations

import json
import sqlite3
from collections import Counter

import pandas as pd
import plotly.graph_objects as go

from markets.profiles import get_market_profile
from sto.structure_similarity import STOStructureSimilarityEngine
from surge.multi_horizon import MULTI_PATTERN_VERSION, SURGE_CLASSES


CLASS_LABELS = {
    "FAST": "FAST · 1~5일",
    "QUICK": "QUICK · 6~10일",
    "SWING": "SWING · 11~15일",
    "POSITION": "POSITION · 16~20일",
}


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE AI Pattern Lab", page_icon="📈", layout="wide")
    _style(st)

    market = st.segmented_control(
        "시장",
        options=["kr", "us"],
        default="kr",
        format_func=lambda value: "한국장" if value == "kr" else "미국장",
        label_visibility="collapsed",
    )
    profile = get_market_profile(str(market or "kr"))

    st.markdown(
        f"""
        <section class="hero">
          <div>
            <div class="eyebrow">ADE · {profile.code.upper()} AI PATTERN LAB</div>
            <h1>급등직전 120일 패턴 탐색</h1>
            <p>현재 차트와 과거 FAST·QUICK·SWING·POSITION 급등직전 패턴을 한 화면에서 비교합니다.</p>
          </div>
          <div class="hero-badge">{profile.name}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if not profile.db_path.exists():
        st.error(f"{profile.db_path}가 없습니다.")
        return

    conn = sqlite3.connect(str(profile.db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "surge_patterns") or not _column_exists(conn, "surge_patterns", "surge_class"):
            st.warning("다중기간 급등직전 패턴 DB가 없습니다.")
            st.code(f"python run_build_surge_patterns.py --market {profile.code} --full", language="bash")
            return

        class_options = [name for name, _, _ in SURGE_CLASSES]
        filter_col, status_col = st.columns([3, 2])
        selected_classes = filter_col.multiselect(
            "패턴 유형",
            class_options,
            default=class_options,
            format_func=lambda value: CLASS_LABELS[value],
        )
        status_col.caption(
            "FAST를 가장 우선하고 QUICK·SWING·POSITION 순으로 속도 가중치가 낮아집니다."
        )
        if not selected_classes:
            st.info("최소 한 개의 급등 유형을 선택하세요.")
            return

        _render_market_summary(st, conn, profile.code, selected_classes)

        recommendations = _latest_recommendations(conn, profile.code)
        if not recommendations:
            st.info("완료된 추천 결과가 없습니다. Picks 화면에서 추천을 먼저 생성하세요.")
            st.markdown("### 패턴 라이브러리")
            st.dataframe(
                pd.DataFrame(_pattern_rows(conn, profile.code, selected_classes, 200)),
                use_container_width=True,
                hide_index=True,
            )
            return

        selected, payload = _recommendation_selector(st, recommendations)
        matches = payload.get("replay_matches") or []
        enriched_matches = _enrich_matches(conn, matches, selected_classes)
        if not enriched_matches:
            st.warning("선택한 유형에 해당하는 매칭 패턴이 없습니다.")
            return

        match, pattern = _match_selector(st, enriched_matches)
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

        current_sto = STOStructureSimilarityEngine().extract(current)
        historical_sto = json.loads(str(pattern["sto_json"]))
        confidence = _confidence_score(match, pattern, enriched_matches)
        class_distribution = Counter(str(item_pattern["surge_class"]) for _, item_pattern in enriched_matches)

        _render_signal_header(st, selected, match, pattern, confidence, class_distribution)

        left, right = st.columns([1.15, 3.85], gap="large")
        with left:
            _render_recommendation_panel(st, recommendations, selected)
            _render_match_panel(st, enriched_matches, pattern)
        with right:
            st.markdown("### 현재 차트 vs 과거 급등직전 패턴")
            st.plotly_chart(
                _comparison_chart(current, historical, selected, pattern),
                use_container_width=True,
                config={"displayModeBar": False},
            )
            st.caption(
                f"현재 {selected['ticker']} 최근 120거래일과 과거 {pattern['ticker']}의 "
                f"{pattern['surge_class']} 급등직전 120거래일을 시작점 대비 등락률로 정규화했습니다."
            )

        lower_left, lower_mid, lower_right = st.columns([1.35, 1.25, 1.4], gap="large")
        with lower_left:
            _render_sto_panel(st, current_sto, historical_sto)
        with lower_mid:
            _render_path_panel(st, pattern)
        with lower_right:
            _render_source_panel(st, pattern)

        with st.expander("전체 급등직전 패턴 라이브러리"):
            st.dataframe(
                pd.DataFrame(_pattern_rows(conn, profile.code, selected_classes, 500)),
                use_container_width=True,
                hide_index=True,
            )
    finally:
        conn.close()


def _style(st) -> None:
    st.markdown(
        """
        <style>
        :root{--ink:#14283d;--muted:#6d8092;--line:rgba(72,119,160,.16);--blue:#2f80ed;--glass:rgba(255,255,255,.78)}
        .stApp{background:radial-gradient(circle at 10% 0%,rgba(112,184,255,.20),transparent 28%),linear-gradient(135deg,#f8fbfe,#eef5fb 52%,#fbfdff);color:var(--ink)}
        .block-container{max-width:1680px;padding-top:1rem;padding-bottom:3rem}
        [data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(249,252,255,.98),rgba(232,242,251,.98));border-right:1px solid var(--line)}
        .hero{display:flex;align-items:center;justify-content:space-between;padding:28px 32px;border-radius:26px;background:linear-gradient(135deg,rgba(255,255,255,.95),rgba(238,247,255,.86));border:1px solid var(--line);box-shadow:0 20px 58px rgba(45,89,127,.11);margin-bottom:18px;overflow:hidden}
        .hero h1{font-size:36px;letter-spacing:-.045em;margin:4px 0 8px}.hero p{margin:0;color:var(--muted)}
        .eyebrow{font-size:12px;letter-spacing:.15em;font-weight:850;color:#2b75b8}
        .hero-badge{padding:12px 18px;border-radius:999px;background:rgba(47,128,237,.09);color:#246aa8;font-weight:850;border:1px solid rgba(47,128,237,.14)}
        .signal-card{padding:20px 22px;border-radius:22px;background:linear-gradient(135deg,rgba(255,255,255,.94),rgba(240,248,255,.84));border:1px solid var(--line);box-shadow:0 12px 34px rgba(50,93,130,.08);height:100%}
        .signal-card .label{font-size:12px;color:var(--muted);font-weight:750;letter-spacing:.06em;text-transform:uppercase}
        .signal-card .value{font-size:28px;font-weight:900;letter-spacing:-.045em;margin-top:7px}.signal-card .sub{color:var(--muted);font-size:13px;margin-top:4px}
        .score-ring{font-size:44px;font-weight:900;letter-spacing:-.05em;color:#176fc1}
        div[data-testid="stMetric"]{background:var(--glass);border:1px solid var(--line);padding:14px 16px;border-radius:18px;box-shadow:0 9px 24px rgba(56,100,139,.06)}
        div[data-testid="stDataFrame"]{border-radius:18px;overflow:hidden;border:1px solid var(--line)}
        div[data-baseweb="select"]>div{border-radius:14px!important;background:rgba(255,255,255,.88)!important;border-color:var(--line)!important}
        h3{letter-spacing:-.03em;color:#18344d;margin-top:1.2rem!important}
        @media(max-width:900px){.hero{padding:22px}.hero h1{font-size:29px}.hero-badge{display:none}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_market_summary(st, conn: sqlite3.Connection, market: str, classes: list[str]) -> None:
    placeholders = ",".join("?" for _ in classes)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS patterns, COUNT(DISTINCT ticker) AS symbols,
               AVG(surge_return_pct) AS avg_return, AVG(target_hit_day) AS avg_days
        FROM surge_patterns
        WHERE market=? AND pattern_version=? AND surge_class IN ({placeholders})
        """,
        (market, MULTI_PATTERN_VERSION, *classes),
    ).fetchone()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("패턴 라이브러리", f"{int(row['patterns'] or 0):,}")
    c2.metric("패턴 보유 종목", f"{int(row['symbols'] or 0):,}")
    c3.metric("평균 최대상승", f"{float(row['avg_return'] or 0):.1f}%")
    c4.metric("평균 30% 도달", f"{float(row['avg_days'] or 0):.1f}일")


def _recommendation_selector(st, recommendations: list[sqlite3.Row]) -> tuple[sqlite3.Row, dict[str, object]]:
    labels = [
        f"#{row['rank_no']}  {row['name'] or row['ticker']}  ·  {float(row['final_similarity']):.1f}%"
        for row in recommendations
    ]
    index = st.selectbox("추천종목", range(len(recommendations)), format_func=lambda i: labels[i])
    selected = recommendations[index]
    return selected, json.loads(str(selected["payload_json"]))


def _match_selector(st, enriched: list[tuple[dict[str, object], sqlite3.Row]]) -> tuple[dict[str, object], sqlite3.Row]:
    labels = [
        f"{pattern['surge_class']} · {item.get('ticker')} · {int(pattern['target_hit_day'])}일 · "
        f"차트 {float(item.get('weekly_similarity', 0)):.1f}% · STO {float(item.get('sto_similarity', 0)):.1f}%"
        for item, pattern in enriched
    ]
    index = st.selectbox("비교 패턴", range(len(enriched)), format_func=lambda i: labels[i])
    return enriched[index]


def _render_signal_header(st, selected, match, pattern, confidence: float, distribution: Counter) -> None:
    average_hit = sum(int(p["target_hit_day"]) for _, p in _safe_pairs(distribution, [])) if False else int(pattern["target_hit_day"])
    cols = st.columns([1.15, 1, 1, 1, 1.25])
    cards = [
        ("추천종목", f"{selected['name'] or selected['ticker']}", str(selected['ticker'])),
        ("패턴 유형", str(pattern["surge_class"]), CLASS_LABELS.get(str(pattern["surge_class"]), "")),
        ("차트 유사도", f"{float(match.get('weekly_similarity', 0)):.1f}%", "최근 120거래일"),
        ("STO 유사도", f"{float(match.get('sto_similarity', 0)):.1f}%", "단·중·장 3계층"),
    ]
    for col, (label, value, sub) in zip(cols[:4], cards):
        col.markdown(
            f'<div class="signal-card"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>',
            unsafe_allow_html=True,
        )
    mix = " · ".join(f"{key} {distribution.get(key, 0)}" for key in ["FAST", "QUICK", "SWING", "POSITION"])
    cols[4].markdown(
        f'<div class="signal-card"><div class="label">Replay Confidence</div><div class="score-ring">{confidence:.0f}</div><div class="sub">{mix}<br>대표 패턴 {average_hit}일 내 30% 도달</div></div>',
        unsafe_allow_html=True,
    )


def _render_recommendation_panel(st, recommendations, selected) -> None:
    st.markdown("### 추천 랭킹")
    rows = []
    for row in recommendations[:12]:
        rows.append({
            "순위": int(row["rank_no"]),
            "종목": row["name"] or row["ticker"],
            "티커": row["ticker"],
            "판정": row["decision"],
            "유사도": float(row["final_similarity"]),
            "선택": "●" if row["ticker"] == selected["ticker"] else "",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=360)


def _render_match_panel(st, enriched, selected_pattern) -> None:
    st.markdown("### 매칭 패턴")
    rows = []
    for item, pattern in enriched:
        rows.append({
            "유형": pattern["surge_class"],
            "과거종목": pattern["name"] or pattern["ticker"],
            "도달일": int(pattern["target_hit_day"]),
            "차트": round(float(item.get("weekly_similarity", 0)), 1),
            "STO": round(float(item.get("sto_similarity", 0)), 1),
            "최대상승": round(float(pattern["surge_return_pct"]), 1),
            "선택": "●" if pattern["pattern_id"] == selected_pattern["pattern_id"] else "",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=290)


def _render_sto_panel(st, current, historical: dict[str, object]) -> None:
    st.markdown("### STO 3계층")
    fig = go.Figure()
    names = ["단기", "중기", "장기"]
    current_values = [current.short, current.middle, current.long]
    historical_values = [float(historical["short"]), float(historical["middle"]), float(historical["long"])]
    fig.add_trace(go.Bar(x=names, y=current_values, name="현재"))
    fig.add_trace(go.Bar(x=names, y=historical_values, name="과거"))
    fig.update_layout(
        barmode="group", height=310, margin=dict(l=8, r=8, t=20, b=10),
        yaxis=dict(range=[0, 100], gridcolor="rgba(90,130,170,.12)"),
        xaxis=dict(showgrid=False), legend=dict(orientation="h", y=1.12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.68)",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"현재 배열 {current.arrangement} · 과거 배열 {historical.get('arrangement', '-')}")


def _render_path_panel(st, pattern) -> None:
    st.markdown("### 급등 경로")
    path = pd.DataFrame({
        "기간": ["5일", "10일", "15일", "20일"],
        "최고상승률": [pattern["return_5d"], pattern["return_10d"], pattern["return_15d"], pattern["return_20d"]],
    })
    fig = go.Figure(go.Bar(x=path["기간"], y=path["최고상승률"], text=path["최고상승률"], textposition="outside"))
    fig.update_layout(
        height=310, margin=dict(l=8, r=8, t=20, b=10), yaxis_title="최고상승률(%)",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.68)",
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="rgba(90,130,170,.12)"),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"속도 가중치 {float(pattern['speed_weight']):.2f} · 30% 최초 도달 {int(pattern['target_hit_day'])}거래일")


def _render_source_panel(st, pattern) -> None:
    st.markdown("### 패턴 출처")
    rows = [
        ("원본 종목", f"{pattern['name'] or pattern['ticker']} ({pattern['ticker']})"),
        ("거래대금 폭발일", pattern["money_event_date"]),
        ("거래대금 배수", f"{float(pattern['money_ratio_120d']):.2f}배"),
        ("패턴 구간", f"{pattern['pattern_start_date']} ~ {pattern['pattern_end_date']}"),
        ("급등 시작", pattern["surge_start_date"]),
        ("급등 최고점", pattern["surge_peak_date"]),
        ("급등 유형", CLASS_LABELS.get(str(pattern["surge_class"]), pattern["surge_class"])),
        ("해당 기간 최대상승", f"+{float(pattern['surge_return_pct']):.2f}%"),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["항목", "값"]), use_container_width=True, hide_index=True, height=310)


def _comparison_chart(current: pd.DataFrame, historical: pd.DataFrame, selected: sqlite3.Row, pattern: sqlite3.Row) -> go.Figure:
    current = current.copy().reset_index(drop=True)
    historical = historical.copy().reset_index(drop=True)
    current_base = float(current.iloc[0]["Close"]) or 1.0
    current["normalized_close"] = (current["Close"].astype(float) / current_base - 1.0) * 100.0
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=list(range(len(current))), y=current["normalized_close"], mode="lines",
        name=f"현재 {selected['ticker']}", line=dict(width=3),
    ))
    figure.add_trace(go.Scatter(
        x=list(range(len(historical))), y=historical["normalized_close"], mode="lines",
        name=f"과거 {pattern['ticker']} {pattern['surge_class']} 직전", line=dict(width=2, dash="dot"),
    ))
    figure.add_hline(y=0, line_width=1, line_dash="dash", line_color="rgba(70,100,130,.25)")
    figure.update_layout(
        height=610, margin=dict(l=18, r=18, t=40, b=20),
        xaxis_title="120거래일 진행", yaxis_title="시작일 대비 등락률(%)",
        hovermode="x unified", legend=dict(orientation="h", y=1.08),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.74)",
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="rgba(90,130,170,.12)")
    return figure


def _confidence_score(match: dict[str, object], pattern: sqlite3.Row, enriched) -> float:
    chart = float(match.get("weekly_similarity", 0))
    sto = float(match.get("sto_similarity", 0))
    sample_bonus = min(6.0, max(0, len(enriched) - 1) * 1.5)
    speed_bonus = float(pattern["speed_weight"] or 0) * 4.0
    return min(99.0, max(0.0, min(chart, sto) * 0.9 + sample_bonus + speed_bonus))


def _enrich_matches(conn: sqlite3.Connection, matches, classes: list[str]):
    enriched = []
    for item in matches:
        pattern = conn.execute("SELECT * FROM surge_patterns WHERE pattern_id=?", (item.get("event_id"),)).fetchone()
        if pattern is not None and str(pattern["surge_class"]) in classes:
            enriched.append((item, pattern))
    return enriched


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


def _pattern_rows(conn: sqlite3.Connection, market: str, classes: list[str], limit: int) -> list[dict[str, object]]:
    placeholders = ",".join("?" for _ in classes)
    rows = conn.execute(
        f"""
        SELECT ticker, name, surge_class, target_hit_day, speed_weight,
               money_event_date, money_ratio_120d, pattern_start_date, pattern_end_date,
               surge_start_date, surge_peak_date, surge_return_pct,
               return_5d, return_10d, return_15d, return_20d, observation_days
        FROM surge_patterns
        WHERE market=? AND pattern_version=? AND surge_class IN ({placeholders})
        ORDER BY speed_weight DESC, surge_return_pct DESC LIMIT ?
        """,
        (market, MULTI_PATTERN_VERSION, *classes, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(str(row[1]) == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _safe_pairs(distribution, fallback):
    return fallback


if __name__ == "__main__":
    run()
