from __future__ import annotations

import json
import sqlite3
from collections import Counter

import pandas as pd
import plotly.graph_objects as go

from markets.profiles import get_market_profile
from sto.layer_engine import STO3LayerEngine
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

    top_left, top_right = st.columns([3, 2])
    market = top_left.segmented_control(
        "시장",
        options=["kr", "us"],
        default="kr",
        format_func=lambda value: "한국장" if value == "kr" else "미국장",
        label_visibility="collapsed",
    )
    view_mode = top_right.segmented_control(
        "화면",
        options=["DESKTOP", "MOBILE"],
        default="DESKTOP",
        format_func=lambda value: "PC 전문가 화면" if value == "DESKTOP" else "휴대폰 실전 화면",
        label_visibility="collapsed",
    )
    mobile = view_mode == "MOBILE"
    profile = get_market_profile(str(market or "kr"))

    st.markdown(
        f"""
        <section class="hero {'mobile-hero' if mobile else ''}">
          <div>
            <div class="eyebrow">ADE · {profile.code.upper()} AI PATTERN LAB</div>
            <h1>급등직전 120일 패턴 탐색</h1>
            <p>현재 차트와 과거 FAST·QUICK·SWING·POSITION 급등직전 패턴을 직접 비교합니다.</p>
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
        selected_classes = st.multiselect(
            "비교할 급등 유형",
            class_options,
            default=class_options,
            format_func=lambda value: CLASS_LABELS[value],
        )
        if not selected_classes:
            st.info("최소 한 개의 급등 유형을 선택하세요.")
            return

        if not mobile:
            _render_market_summary(st, conn, profile.code, selected_classes)

        recommendations = _latest_recommendations(conn, profile.code)
        if not recommendations:
            st.info("완료된 추천 결과가 없습니다. Picks 화면에서 추천을 먼저 생성하세요.")
            st.dataframe(
                pd.DataFrame(_pattern_rows(conn, profile.code, selected_classes, 200)),
                use_container_width=True,
                hide_index=True,
            )
            return

        selected = _recommendation_cards(st, recommendations, mobile)
        payload = json.loads(str(selected["payload_json"]))
        matches = payload.get("replay_matches") or []
        enriched = _enrich_matches(conn, matches, selected_classes)
        if not enriched:
            st.warning("선택한 급등 유형에 해당하는 매칭 패턴이 없습니다.")
            return

        match, pattern = _pattern_cards(st, enriched, mobile)
        current = _current_bars(conn, profile.code, str(selected["ticker"]), profile.price_source)
        historical = pd.DataFrame(
            [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM surge_pattern_bars WHERE pattern_id=? ORDER BY day_index",
                    (pattern["pattern_id"],),
                ).fetchall()
            ]
        )
        if current.empty or historical.empty:
            st.error("비교 차트 데이터가 부족합니다.")
            return

        current_structure = STOStructureSimilarityEngine().extract(current)
        historical_structure = json.loads(str(pattern["sto_json"]))
        class_distribution = Counter(str(row["surge_class"]) for _, row in enriched)
        confidence = _confidence_score(match, pattern, enriched)
        overall = _overall_score(match, pattern, confidence, len(enriched))
        reasons = _recommendation_reasons(payload, match, pattern, confidence, overall, class_distribution)

        _render_decision_summary(
            st,
            selected,
            match,
            pattern,
            overall,
            confidence,
            class_distribution,
            reasons,
            mobile,
        )

        if mobile:
            _render_mobile_layout(
                st,
                current,
                historical,
                selected,
                pattern,
                match,
                current_structure,
                historical_structure,
                reasons,
            )
        else:
            _render_desktop_layout(
                st,
                current,
                historical,
                selected,
                pattern,
                match,
                current_structure,
                historical_structure,
                enriched,
                reasons,
            )

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
        :root{--ink:#14283d;--muted:#6d8092;--line:rgba(72,119,160,.16);--blue:#2f80ed;--glass:rgba(255,255,255,.80)}
        .stApp{background:radial-gradient(circle at 10% 0%,rgba(112,184,255,.20),transparent 28%),linear-gradient(135deg,#f8fbfe,#eef5fb 52%,#fbfdff);color:var(--ink)}
        .block-container{max-width:1680px;padding-top:1rem;padding-bottom:3rem}
        [data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(249,252,255,.98),rgba(232,242,251,.98));border-right:1px solid var(--line)}
        .hero{display:flex;align-items:center;justify-content:space-between;padding:28px 32px;border-radius:26px;background:linear-gradient(135deg,rgba(255,255,255,.95),rgba(238,247,255,.86));border:1px solid var(--line);box-shadow:0 20px 58px rgba(45,89,127,.11);margin-bottom:18px}
        .hero h1{font-size:36px;letter-spacing:-.045em;margin:4px 0 8px}.hero p{margin:0;color:var(--muted)}
        .eyebrow{font-size:12px;letter-spacing:.15em;font-weight:850;color:#2b75b8}
        .hero-badge{padding:12px 18px;border-radius:999px;background:rgba(47,128,237,.09);color:#246aa8;font-weight:850;border:1px solid rgba(47,128,237,.14)}
        .summary-card{padding:18px 20px;border-radius:21px;background:linear-gradient(135deg,rgba(255,255,255,.95),rgba(239,248,255,.86));border:1px solid var(--line);box-shadow:0 11px 30px rgba(50,93,130,.07);height:100%}
        .summary-card .label{font-size:11px;color:var(--muted);font-weight:800;letter-spacing:.08em;text-transform:uppercase}
        .summary-card .value{font-size:29px;font-weight:900;letter-spacing:-.045em;margin-top:6px}.summary-card .sub{color:var(--muted);font-size:12px;margin-top:3px}
        .overall-card{padding:22px;border-radius:24px;background:linear-gradient(145deg,rgba(225,242,255,.96),rgba(255,255,255,.93));border:1px solid rgba(47,128,237,.20);box-shadow:0 16px 42px rgba(42,101,151,.12)}
        .overall-score{font-size:56px;font-weight:950;line-height:1;color:#176fc1;letter-spacing:-.06em}
        .reason-box{padding:16px 18px;border-radius:18px;background:rgba(255,255,255,.75);border:1px solid var(--line);margin-bottom:8px;color:#28445d}
        div[data-testid="stButton"] button{min-height:82px;border-radius:19px!important;text-align:left!important;justify-content:flex-start!important;padding:13px 15px!important;background:linear-gradient(135deg,rgba(255,255,255,.95),rgba(239,247,255,.88))!important;border:1px solid var(--line)!important;box-shadow:0 8px 22px rgba(56,100,139,.06)!important;font-weight:800!important;white-space:pre-line!important}
        div[data-testid="stButton"] button[kind="primary"]{background:linear-gradient(135deg,#dceeff,#f3f9ff)!important;border-color:rgba(47,128,237,.38)!important;color:#145f9f!important;box-shadow:0 11px 28px rgba(47,128,237,.13)!important}
        div[data-testid="stMetric"]{background:var(--glass);border:1px solid var(--line);padding:14px 16px;border-radius:18px}
        div[data-testid="stDataFrame"]{border-radius:18px;overflow:hidden;border:1px solid var(--line)}
        div[data-baseweb="select"]>div{border-radius:14px!important;background:rgba(255,255,255,.88)!important;border-color:var(--line)!important}
        h3{letter-spacing:-.03em;color:#18344d;margin-top:1.2rem!important}
        @media(max-width:900px){
          .block-container{padding:.65rem .65rem 2rem}.hero{padding:20px;border-radius:21px}.hero h1{font-size:27px}.hero p{font-size:13px}.hero-badge{display:none}
          .summary-card{padding:15px}.summary-card .value{font-size:24px}.overall-score{font-size:47px}
          div[data-testid="stButton"] button{min-height:72px!important;font-size:.88rem!important}
          [data-testid="stSidebar"]{min-width:250px}
        }
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
    cols = st.columns(4)
    values = [
        ("패턴 라이브러리", f"{int(row['patterns'] or 0):,}"),
        ("패턴 보유 종목", f"{int(row['symbols'] or 0):,}"),
        ("평균 최대상승", f"{float(row['avg_return'] or 0):.1f}%"),
        ("평균 30% 도달", f"{float(row['avg_days'] or 0):.1f}일"),
    ]
    for col, (label, value) in zip(cols, values):
        col.metric(label, value)


def _recommendation_cards(st, recommendations: list[sqlite3.Row], mobile: bool) -> sqlite3.Row:
    st.markdown("### 추천종목")
    key = "pattern_lab_selected_ticker"
    tickers = [str(row["ticker"]) for row in recommendations]
    if st.session_state.get(key) not in tickers:
        st.session_state[key] = tickers[0]

    visible = recommendations[:6 if mobile else 12]
    columns_per_row = 1 if mobile else 3
    for start in range(0, len(visible), columns_per_row):
        cols = st.columns(columns_per_row)
        for col, row in zip(cols, visible[start : start + columns_per_row]):
            ticker = str(row["ticker"])
            active = ticker == st.session_state[key]
            label = (
                f"#{int(row['rank_no'])}  {row['name'] or ticker}\n"
                f"{ticker}  ·  {row['decision']}  ·  유사도 {float(row['final_similarity']):.1f}%"
            )
            if col.button(label, key=f"rec_card_{ticker}", type="primary" if active else "secondary", use_container_width=True):
                st.session_state[key] = ticker
                st.rerun()
    return next(row for row in recommendations if str(row["ticker"]) == st.session_state[key])


def _pattern_cards(st, enriched: list[tuple[dict[str, object], sqlite3.Row]], mobile: bool):
    st.markdown("### 비교할 과거 급등직전 패턴")
    key = "pattern_lab_selected_pattern"
    ids = [str(pattern["pattern_id"]) for _, pattern in enriched]
    if st.session_state.get(key) not in ids:
        st.session_state[key] = ids[0]

    visible = enriched[:4 if mobile else 8]
    columns_per_row = 1 if mobile else 4
    for start in range(0, len(visible), columns_per_row):
        cols = st.columns(columns_per_row)
        for col, (item, pattern) in zip(cols, visible[start : start + columns_per_row]):
            pattern_id = str(pattern["pattern_id"])
            active = pattern_id == st.session_state[key]
            label = (
                f"{pattern['surge_class']}  ·  {pattern['name'] or pattern['ticker']}\n"
                f"30% {int(pattern['target_hit_day'])}일  ·  차트 {float(item.get('weekly_similarity', 0)):.1f}%  ·  STO {float(item.get('sto_similarity', 0)):.1f}%"
            )
            if col.button(label, key=f"pattern_card_{pattern_id}", type="primary" if active else "secondary", use_container_width=True):
                st.session_state[key] = pattern_id
                st.rerun()
    return next(pair for pair in enriched if str(pair[1]["pattern_id"]) == st.session_state[key])


def _render_decision_summary(st, selected, match, pattern, overall, confidence, distribution, reasons, mobile) -> None:
    st.markdown("### AI 의사결정 요약")
    if mobile:
        st.markdown(
            f"""
            <div class="overall-card">
              <div class="eyebrow">OVERALL SCORE</div>
              <div class="overall-score">{overall:.0f}</div>
              <b>{selected['name'] or selected['ticker']}</b> · {pattern['surge_class']} · {int(pattern['target_hit_day'])}일 내 30% 도달 패턴<br>
              <span style="color:#6d8092">Confidence {confidence:.0f} · 차트 {float(match.get('weekly_similarity',0)):.1f}% · STO {float(match.get('sto_similarity',0)):.1f}%</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    left, right = st.columns([1.15, 3.85], gap="large")
    left.markdown(
        f"""
        <div class="overall-card">
          <div class="eyebrow">OVERALL SCORE</div>
          <div class="overall-score">{overall:.0f}</div>
          <b>{selected['name'] or selected['ticker']}</b><br>
          <span style="color:#6d8092">Replay Confidence {confidence:.0f}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cards = right.columns(4)
    mix = " · ".join(f"{name} {distribution.get(name, 0)}" for name in ["FAST", "QUICK", "SWING", "POSITION"])
    values = [
        ("급등 유형", str(pattern["surge_class"]), f"30% 도달 {int(pattern['target_hit_day'])}일"),
        ("차트 유사도", f"{float(match.get('weekly_similarity', 0)):.1f}%", "최근 120거래일"),
        ("STO 유사도", f"{float(match.get('sto_similarity', 0)):.1f}%", "단·중·장 3계층"),
        ("근거 사례", f"{sum(distribution.values())}건", mix),
    ]
    for col, (label, value, sub) in zip(cards, values):
        col.markdown(
            f'<div class="summary-card"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>',
            unsafe_allow_html=True,
        )


def _render_desktop_layout(st, current, historical, selected, pattern, match, current_structure, historical_structure, enriched, reasons) -> None:
    main, side = st.columns([3.8, 1.2], gap="large")
    with main:
        st.markdown("### 현재 차트 vs 과거 급등직전 패턴")
        st.plotly_chart(_comparison_chart(current, historical, selected, pattern, 610), use_container_width=True, config={"displayModeBar": False})
    with side:
        st.markdown("### 추천 근거")
        for reason in reasons[:6]:
            st.markdown(f'<div class="reason-box">{reason}</div>', unsafe_allow_html=True)

    sto_col, path_col = st.columns([2.3, 1], gap="large")
    with sto_col:
        _render_sto_flow(st, current, historical, height=390)
    with path_col:
        _render_path_panel(st, pattern, height=390)

    detail_left, detail_right = st.columns([1.25, 1], gap="large")
    with detail_left:
        _render_match_table(st, enriched, pattern)
    with detail_right:
        _render_source_panel(st, pattern)


def _render_mobile_layout(st, current, historical, selected, pattern, match, current_structure, historical_structure, reasons) -> None:
    st.markdown("### 현재 vs 과거 패턴")
    st.plotly_chart(_comparison_chart(current, historical, selected, pattern, 420), use_container_width=True, config={"displayModeBar": False})

    metrics = st.columns(2)
    metrics[0].metric("차트 유사도", f"{float(match.get('weekly_similarity', 0)):.1f}%")
    metrics[1].metric("STO 유사도", f"{float(match.get('sto_similarity', 0)):.1f}%")
    metrics = st.columns(2)
    metrics[0].metric("급등 유형", str(pattern["surge_class"]))
    metrics[1].metric("30% 최초 도달", f"{int(pattern['target_hit_day'])}일")

    st.markdown("### STO 120일 흐름")
    st.plotly_chart(_sto_flow_chart(current, historical, 390), use_container_width=True, config={"displayModeBar": False})

    with st.expander("추천 근거", expanded=True):
        for reason in reasons[:6]:
            st.markdown(f"- {reason}")
    with st.expander("과거 상승 경로"):
        _render_path_panel(st, pattern, height=300)
    with st.expander("패턴 출처"):
        _render_source_panel(st, pattern)


def _comparison_chart(current: pd.DataFrame, historical: pd.DataFrame, selected, pattern, height: int) -> go.Figure:
    current = current.copy().reset_index(drop=True)
    historical = historical.copy().reset_index(drop=True)
    current_base = float(current.iloc[0]["Close"]) or 1.0
    historical_base = float(historical.iloc[0]["close"]) or 1.0
    current_values = (current["Close"].astype(float) / current_base - 1.0) * 100.0
    historical_values = (historical["close"].astype(float) / historical_base - 1.0) * 100.0
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=list(range(len(current_values))), y=current_values, mode="lines", name=f"현재 {selected['ticker']}", line=dict(width=3)))
    figure.add_trace(go.Scatter(x=list(range(len(historical_values))), y=historical_values, mode="lines", name=f"과거 {pattern['ticker']} {pattern['surge_class']}", line=dict(width=2, dash="dot")))
    figure.add_hline(y=0, line_width=1, line_dash="dash", line_color="rgba(70,100,130,.25)")
    figure.update_layout(
        height=height, margin=dict(l=18, r=18, t=40, b=20),
        xaxis_title="120거래일 진행", yaxis_title="시작일 대비 등락률(%)",
        hovermode="x unified", legend=dict(orientation="h", y=1.08),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.74)",
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="rgba(90,130,170,.12)")
    return figure


def _sto_series(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    rename = {"trade_date": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    frame = frame.rename(columns=rename)
    engine = STO3LayerEngine()
    weekly = engine._to_weekly(frame)
    return pd.DataFrame({
        "short": engine._stochastic(weekly, 5),
        "middle": engine._stochastic(weekly, 14),
        "long": engine._stochastic(weekly, 34),
    }).reset_index(drop=True)


def _sto_flow_chart(current: pd.DataFrame, historical: pd.DataFrame, height: int) -> go.Figure:
    current_series = _sto_series(current)
    historical_series = _sto_series(historical)
    figure = go.Figure()
    styles = {"short": ("단기", 3), "middle": ("중기", 2), "long": ("장기", 2)}
    for key, (label, width) in styles.items():
        figure.add_trace(go.Scatter(x=list(range(len(current_series))), y=current_series[key], mode="lines", name=f"현재 {label}", line=dict(width=width)))
        figure.add_trace(go.Scatter(x=list(range(len(historical_series))), y=historical_series[key], mode="lines", name=f"과거 {label}", line=dict(width=width, dash="dot")))
    figure.add_hline(y=80, line_dash="dash", line_width=1, line_color="rgba(190,80,80,.25)")
    figure.add_hline(y=20, line_dash="dash", line_width=1, line_color="rgba(60,130,190,.25)")
    figure.update_layout(
        height=height, margin=dict(l=12, r=12, t=25, b=15),
        yaxis=dict(range=[0, 100], title="STO", gridcolor="rgba(90,130,170,.12)"),
        xaxis=dict(title="120일 구간의 주차", showgrid=False),
        hovermode="x unified", legend=dict(orientation="h", y=1.15),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.70)",
    )
    return figure


def _render_sto_flow(st, current, historical, height: int) -> None:
    st.markdown("### STO 120일 흐름 비교")
    st.plotly_chart(_sto_flow_chart(current, historical, height), use_container_width=True, config={"displayModeBar": False})
    st.caption("실선은 현재 종목, 점선은 과거 급등직전 패턴입니다. 단기·중기·장기 STO를 같은 시간축에서 비교합니다.")


def _render_path_panel(st, pattern, height: int) -> None:
    st.markdown("### 과거 급등 경로")
    path = pd.DataFrame({
        "기간": ["5일", "10일", "15일", "20일"],
        "최고상승률": [pattern["return_5d"], pattern["return_10d"], pattern["return_15d"], pattern["return_20d"]],
    })
    fig = go.Figure(go.Bar(x=path["기간"], y=path["최고상승률"], text=path["최고상승률"], textposition="outside"))
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=20, b=10), yaxis_title="최고상승률(%)",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.68)",
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="rgba(90,130,170,.12)"),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"속도 가중치 {float(pattern['speed_weight']):.2f} · 30% 최초 도달 {int(pattern['target_hit_day'])}거래일")


def _render_match_table(st, enriched, selected_pattern) -> None:
    st.markdown("### 매칭 근거 사례")
    rows = []
    for item, pattern in enriched:
        rows.append({
            "유형": pattern["surge_class"], "과거종목": pattern["name"] or pattern["ticker"],
            "도달일": int(pattern["target_hit_day"]), "차트": round(float(item.get("weekly_similarity", 0)), 1),
            "STO": round(float(item.get("sto_similarity", 0)), 1), "최대상승": round(float(pattern["surge_return_pct"]), 1),
            "선택": "●" if pattern["pattern_id"] == selected_pattern["pattern_id"] else "",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=300)


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
    st.dataframe(pd.DataFrame(rows, columns=["항목", "값"]), use_container_width=True, hide_index=True, height=300)


def _overall_score(match: dict[str, object], pattern: sqlite3.Row, confidence: float, sample_count: int) -> float:
    chart = float(match.get("weekly_similarity", 0))
    sto = float(match.get("sto_similarity", 0))
    speed = float(pattern["speed_weight"] or 0) * 100.0
    evidence = min(100.0, 55.0 + sample_count * 9.0)
    return round(min(99.0, chart * 0.35 + sto * 0.30 + speed * 0.15 + evidence * 0.20), 1)


def _confidence_score(match: dict[str, object], pattern: sqlite3.Row, enriched) -> float:
    chart = float(match.get("weekly_similarity", 0))
    sto = float(match.get("sto_similarity", 0))
    sample_bonus = min(6.0, max(0, len(enriched) - 1) * 1.5)
    speed_bonus = float(pattern["speed_weight"] or 0) * 4.0
    return min(99.0, max(0.0, min(chart, sto) * 0.9 + sample_bonus + speed_bonus))


def _recommendation_reasons(payload, match, pattern, confidence, overall, distribution) -> list[str]:
    reasons = [
        f"Overall Score {overall:.1f}점, Replay Confidence {confidence:.1f}점입니다.",
        f"현재 120일 차트가 과거 급등직전 패턴과 {float(match.get('weekly_similarity', 0)):.1f}% 유사합니다.",
        f"STO 단기·중기·장기 구조 유사도는 {float(match.get('sto_similarity', 0)):.1f}%입니다.",
        f"대표 사례는 {pattern['surge_class']} 유형으로 {int(pattern['target_hit_day'])}거래일 만에 30%에 도달했습니다.",
        "매칭 분포: " + " · ".join(f"{name} {distribution.get(name, 0)}건" for name in ["FAST", "QUICK", "SWING", "POSITION"]),
        f"대표 과거 사례의 해당 기간 최대상승률은 +{float(pattern['surge_return_pct']):.1f}%입니다.",
    ]
    stored = payload.get("reasons") or []
    for item in stored:
        text = str(item)
        if text not in reasons:
            reasons.append(text)
    return reasons


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


if __name__ == "__main__":
    run()
