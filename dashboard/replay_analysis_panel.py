from __future__ import annotations

import math
import sqlite3
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard.charts import CHART_CONFIG, build_pattern_compare_chart, stochastic_ohlc


def _number(value: object) -> float | None:
    try:
        if value is None or str(value) == "":
            return None
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    except (TypeError, ValueError):
        return None


def _dedupe_replay_matches(replay_matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for match in replay_matches:
        ids = _match_ids(match)
        identity = ids[0] if ids else ""
        ticker = str(match.get("ticker") or match.get("name") or "").strip()
        event_date = str(match.get("event_date") or "").strip()
        key = (identity, ticker, event_date)
        if key in seen:
            continue
        seen.add(key)
        unique.append(match)
    return unique


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.Error:
        return 0


def _match_ids(match: dict[str, Any]) -> list[str]:
    values = [match.get("source_event_id"), match.get("event_id"), match.get("pattern_id")]
    return [str(value).strip() for value in values if str(value or "").strip()]


def _pattern_for_match(conn: sqlite3.Connection, match: dict[str, Any]):
    if not _table_exists(conn, "surge_patterns"):
        return None
    columns = _table_columns(conn, "surge_patterns")
    for event_id in _match_ids(match):
        for column in ("source_event_id", "pattern_id"):
            if column not in columns:
                continue
            try:
                row = conn.execute(
                    f"SELECT * FROM surge_patterns WHERE {column}=? ORDER BY surge_start_date DESC LIMIT 1",
                    (event_id,),
                ).fetchone()
            except sqlite3.Error:
                row = None
            if row is not None:
                return row
    return None


def _pattern_bars(conn: sqlite3.Connection, pattern) -> pd.DataFrame:
    if pattern is None or not _table_exists(conn, "surge_pattern_bars"):
        return pd.DataFrame()
    pattern_id = str(pattern["pattern_id"] if "pattern_id" in pattern.keys() else "")
    if not pattern_id:
        return pd.DataFrame()
    try:
        rows = conn.execute(
            "SELECT * FROM surge_pattern_bars WHERE pattern_id=? ORDER BY bar_index",
            (pattern_id,),
        ).fetchall()
    except sqlite3.Error:
        return pd.DataFrame()
    return pd.DataFrame([dict(row) for row in rows])


def _load_future_rows(conn: sqlite3.Connection, match: dict[str, Any]):
    if not _table_exists(conn, "replay_event_flow"):
        return []
    for event_id in _match_ids(match):
        try:
            rows = conn.execute(
                "SELECT day_index, close FROM replay_event_flow WHERE event_id=? ORDER BY day_index",
                (event_id,),
            ).fetchall()
        except sqlite3.Error:
            rows = []
        if rows:
            return rows
    return []


def _future_paths(conn: sqlite3.Connection, replay_matches: list[dict[str, Any]]) -> pd.DataFrame:
    if not replay_matches:
        return pd.DataFrame()
    samples: dict[str, list[float]] = {}
    for index, match in enumerate(replay_matches, start=1):
        rows = _load_future_rows(conn, match)
        if not rows:
            continue
        future_week = int(match.get("future_start_week_index") or 0)
        start_day = max(0, future_week * 5)
        future = [row for row in rows if int(row["day_index"]) >= start_day][:21]
        if len(future) < 2:
            continue
        entry = float(future[0]["close"] or 0)
        if entry <= 0:
            continue
        event_id = next(iter(_match_ids(match)), f"case-{index}")
        name = str(match.get("name") or match.get("ticker") or event_id)
        event_date = str(match.get("event_date") or "-")
        label = f"#{index} {name} · {event_date} · {event_id}"
        samples[label] = [round((float(row["close"]) / entry - 1.0) * 100.0, 4) for row in future]
    if not samples:
        return pd.DataFrame()
    frame = pd.DataFrame({name: pd.Series(values) for name, values in samples.items()})
    frame.index.name = "거래일"
    return frame


def _format_pct(value: object) -> str:
    numeric = _number(value)
    return "-" if numeric is None else f"{numeric:+.2f}%"


def _mean_pct(series: pd.Series) -> str:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return "-" if clean.empty else f"{clean.mean():+.2f}%"


def _classify_case(match: dict[str, Any]) -> str:
    final_return = _number(match.get("final_return") or match.get("return_20d") or match.get("future_return"))
    max_return = _number(match.get("max_return"))
    max_drawdown = _number(match.get("max_drawdown"))
    if final_return is not None:
        if final_return >= 5:
            return "성공"
        if final_return <= -5:
            return "실패"
    if max_return is not None and max_return >= 10 and (max_drawdown is None or max_drawdown > -10):
        return "성공"
    if max_drawdown is not None and max_drawdown <= -10:
        return "실패"
    return "중립"


def _normalize_ohlcv(frame: pd.DataFrame, *, historical: bool = False) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    source = frame.copy()
    mapping = {
        "Date": ["Date", "date", "datetime", "timestamp", "bar_index"],
        "Open": ["Open", "open"],
        "High": ["High", "high"],
        "Low": ["Low", "low"],
        "Close": ["Close", "close"],
        "Volume": ["Volume", "volume"],
    }
    normalized = pd.DataFrame()
    for target, candidates in mapping.items():
        chosen = next((column for column in candidates if column in source.columns), None)
        if chosen is None:
            if target == "Volume":
                normalized[target] = 0.0
                continue
            return pd.DataFrame()
        normalized[target] = source[chosen]
    if historical and "bar_index" in source.columns:
        normalized["Date"] = pd.to_numeric(source["bar_index"], errors="coerce")
    else:
        parsed = pd.to_datetime(normalized["Date"], errors="coerce")
        if parsed.notna().any():
            normalized["Date"] = parsed
        else:
            normalized["Date"] = range(len(normalized))
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)


def _build_direct_compare_chart(
    current: pd.DataFrame,
    historical: pd.DataFrame,
    current_label: str,
    historical_label: str,
) -> go.Figure:
    current_df = _normalize_ohlcv(current)
    historical_df = _normalize_ohlcv(historical, historical=True)
    length = min(len(current_df), len(historical_df), 80)
    if length < 5:
        return go.Figure()
    current_df = current_df.tail(length).reset_index(drop=True)
    historical_df = historical_df.tail(length).reset_index(drop=True)
    x = list(range(length))

    def normalized_close(frame: pd.DataFrame) -> pd.Series:
        start = float(frame.iloc[0]["Close"])
        return frame["Close"].astype(float) / start * 100.0

    def volume_ratio(frame: pd.DataFrame) -> pd.Series:
        average = frame["Volume"].rolling(20, min_periods=1).mean().replace(0, 1)
        return frame["Volume"] / average * 100.0

    current_price = normalized_close(current_df)
    historical_price = normalized_close(historical_df)
    current_volume = volume_ratio(current_df)
    historical_volume = volume_ratio(historical_df)

    fig = make_subplots(
        rows=6,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.018,
        row_heights=[0.27, 0.27, 0.14, 0.14, 0.09, 0.09],
        subplot_titles=(
            f"현재 {current_label} · 가격",
            f"과거 {historical_label} · 가격",
            "현재 vs 과거 · 기준 100 Overlay",
            "거래량 · 20봉 평균 대비",
            "STO 5·3·3",
            "STO 10·6·6 / 20·12·12",
        ),
    )
    fig.add_trace(go.Candlestick(x=x, open=current_df["Open"], high=current_df["High"], low=current_df["Low"], close=current_df["Close"], name=f"현재 {current_label}"), row=1, col=1)
    fig.add_trace(go.Candlestick(x=x, open=historical_df["Open"], high=historical_df["High"], low=historical_df["Low"], close=historical_df["Close"], name=f"과거 {historical_label}"), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=current_price, mode="lines", name="현재 정규화", line=dict(width=2.4)), row=3, col=1)
    fig.add_trace(go.Scatter(x=x, y=historical_price, mode="lines", name="과거 정규화", line=dict(width=2.0, dash="dot")), row=3, col=1)
    fig.add_trace(go.Scatter(x=x, y=current_volume, mode="lines", name="현재 거래량 배수"), row=4, col=1)
    fig.add_trace(go.Scatter(x=x, y=historical_volume, mode="lines", name="과거 거래량 배수", line=dict(dash="dot")), row=4, col=1)

    for row_index, period, smooth in [(5, 5, 3), (6, 10, 6), (6, 20, 12)]:
        ck, cd = stochastic_ohlc(current_df, period=period, smooth=smooth)
        hk, hd = stochastic_ohlc(historical_df, period=period, smooth=smooth)
        suffix = f"{period}·{smooth}"
        fig.add_trace(go.Scatter(x=x, y=ck, mode="lines", name=f"현재 K {suffix}", line=dict(width=1.6)), row=row_index, col=1)
        fig.add_trace(go.Scatter(x=x, y=cd, mode="lines", name=f"현재 D {suffix}", line=dict(width=1.2, dash="dash")), row=row_index, col=1)
        fig.add_trace(go.Scatter(x=x, y=hk, mode="lines", name=f"과거 K {suffix}", line=dict(width=1.3, dash="dot")), row=row_index, col=1)
        fig.add_trace(go.Scatter(x=x, y=hd, mode="lines", name=f"과거 D {suffix}", line=dict(width=1.0, dash="dashdot")), row=row_index, col=1)

    for row_index in (5, 6):
        fig.add_hline(y=80, line_dash="dot", row=row_index, col=1)
        fig.add_hline(y=20, line_dash="dot", row=row_index, col=1)
        fig.update_yaxes(range=[0, 100], row=row_index, col=1)

    fig.update_layout(
        height=1060,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        xaxis2_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02),
        margin=dict(l=16, r=20, t=90, b=20),
        title="추천 근거 원천 데이터 직접 비교",
    )
    fig.update_xaxes(title_text="대응 봉 위치", row=6, col=1)
    fig.update_yaxes(title_text="가격", row=1, col=1)
    fig.update_yaxes(title_text="가격", row=2, col=1)
    fig.update_yaxes(title_text="기준 100", row=3, col=1)
    fig.update_yaxes(title_text="평균 대비 %", row=4, col=1)
    return fig


def _data_availability(
    conn: sqlite3.Connection,
    current: pd.DataFrame,
    replay_matches: list[dict[str, Any]],
    prediction: dict[str, Any],
) -> list[dict[str, str]]:
    current_ohlcv = _normalize_ohlcv(current)
    pattern_count = _table_count(conn, "surge_patterns")
    pattern_bar_count = _table_count(conn, "surge_pattern_bars")
    future_count = _table_count(conn, "replay_event_flow")
    pattern_columns = _table_columns(conn, "surge_pattern_bars")
    flow_columns = _table_columns(conn, "replay_event_flow")

    current_state = "사용 가능" if len(current_ohlcv) >= 5 else "부족"
    replay_state = "사용 가능" if replay_matches else "없음"
    pattern_state = "사용 가능" if pattern_count > 0 and pattern_bar_count > 0 else "없음"
    future_state = "사용 가능" if future_count > 0 and {"day_index", "close"}.issubset(flow_columns) else "없음"
    prediction_state = "사용 가능" if prediction else "없음"
    volume_state = "사용 가능" if "volume" in pattern_columns or "Volume" in pattern_columns else "없음"

    investor_tables = [
        "investor_trading",
        "investor_flow",
        "investor_flows",
        "market_investor_flow",
        "stock_investor_flow",
    ]
    environment_tables = [
        "market_environment",
        "market_snapshot",
        "environment_snapshots",
        "macro_snapshot",
        "sector_snapshot",
        "events",
        "market_events",
    ]
    investor_found = [table for table in investor_tables if _table_count(conn, table) > 0]
    environment_found = [table for table in environment_tables if _table_count(conn, table) > 0]

    return [
        {"데이터": "현재 종목 OHLCV", "상태": current_state, "확인 내용": f"현재 화면 전달 봉 {len(current_ohlcv)}개"},
        {"데이터": "Replay 매칭 결과", "상태": replay_state, "확인 내용": f"중복 제거 후 {len(replay_matches)}건"},
        {"데이터": "과거 패턴 원천 봉", "상태": pattern_state, "확인 내용": f"surge_patterns {pattern_count:,}건 / surge_pattern_bars {pattern_bar_count:,}건"},
        {"데이터": "과거 거래량", "상태": volume_state, "확인 내용": "surge_pattern_bars의 volume 열 확인"},
        {"데이터": "매칭 이후 경로", "상태": future_state, "확인 내용": f"replay_event_flow {future_count:,}건"},
        {"데이터": "Prediction", "상태": prediction_state, "확인 내용": "payload prediction 존재 여부"},
        {"데이터": "투자자별 수급", "상태": "사용 가능" if investor_found else "미확인/없음", "확인 내용": ", ".join(investor_found) if investor_found else "후보 테이블을 찾지 못함"},
        {"데이터": "시장·업종·이벤트 환경", "상태": "사용 가능" if environment_found else "미확인/없음", "확인 내용": ", ".join(environment_found) if environment_found else "후보 테이블을 찾지 못함"},
    ]


def _render_data_availability(rows: list[dict[str, str]]) -> None:
    missing = [row for row in rows if row["상태"] != "사용 가능"]
    if missing:
        st.warning("검증 신뢰도를 낮추는 미연결 데이터가 있습니다: " + ", ".join(row["데이터"] for row in missing))
    with st.expander("데이터 연결 진단", expanded=False):
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_validation_map(replay_matches: list[dict[str, Any]], prediction: dict[str, Any]) -> None:
    weekly_values = [_number(item.get("weekly_similarity")) for item in replay_matches]
    sto_values = [_number(item.get("sto_similarity")) for item in replay_matches]
    rows = [
        {"계산 결과": "주봉 패턴", "값": _mean_pct(pd.Series(weekly_values)), "직접 확인": "현재·과거 가격 흐름 / Overlay / 거래량"},
        {"계산 결과": "STO", "값": _mean_pct(pd.Series(sto_values)), "직접 확인": "5·3·3 / 10·6·6 / 20·12·12 전환 시점"},
        {"계산 결과": "Replay", "값": f"{len(replay_matches)}건", "직접 확인": "성공·중립·실패 사례와 사후 경로"},
        {"계산 결과": "Prediction", "값": str(prediction.get("grade") or "-") if prediction else "-", "직접 확인": "기간별 기대수익과 경로 분산"},
    ]
    with st.expander("알고리즘 계산값 ↔ 원천 데이터 대응표", expanded=False):
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_replay_overview(replay_matches: list[dict[str, Any]]) -> None:
    if not replay_matches:
        return
    frame = pd.DataFrame(
        [
            {
                "weekly": _number(match.get("weekly_similarity")),
                "sto": _number(match.get("sto_similarity")),
                "max_return": _number(match.get("max_return")),
                "max_drawdown": _number(match.get("max_drawdown")),
            }
            for match in replay_matches[:10]
        ]
    )
    drawdowns = pd.to_numeric(frame["max_drawdown"], errors="coerce").dropna()
    returns = pd.to_numeric(frame["max_return"], errors="coerce").dropna()
    metrics = st.columns(5)
    metrics[0].metric("유효 사례", f"{len(frame)}건")
    metrics[1].metric("평균 주봉", _mean_pct(frame["weekly"]))
    metrics[2].metric("평균 STO", _mean_pct(frame["sto"]))
    metrics[3].metric("평균 최고수익", _mean_pct(frame["max_return"]))
    metrics[4].metric("최대 하락", _format_pct(drawdowns.min() if not drawdowns.empty else None))


def _render_outcome_groups(replay_matches: list[dict[str, Any]]) -> None:
    rows = []
    for match in replay_matches[:10]:
        rows.append(
            {
                "결과": _classify_case(match),
                "종목": match.get("name") or match.get("ticker") or "-",
                "기준일": match.get("event_date") or "-",
                "주봉유사도(%)": _number(match.get("weekly_similarity")),
                "STO유사도(%)": _number(match.get("sto_similarity")),
                "최고수익(%)": _number(match.get("max_return")),
                "최대하락(%)": _number(match.get("max_drawdown")),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return
    with st.expander("성공·중립·실패 전체 사례", expanded=False):
        tabs = st.tabs(["성공", "중립", "실패"])
        for tab, label in zip(tabs, ["성공", "중립", "실패"]):
            with tab:
                subset = frame[frame["결과"] == label]
                if subset.empty:
                    st.caption(f"{label} 사례가 없습니다.")
                else:
                    st.dataframe(subset, hide_index=True, use_container_width=True)


def _render_prediction(prediction: dict[str, Any]) -> None:
    horizons = prediction.get("horizons") or []
    rows = []
    for item in horizons:
        if isinstance(item, dict):
            rows.append(
                {
                    "기간": f"{int(item.get('days') or 0)}일",
                    "표본": int(item.get("sample_count") or 0),
                    "상승확률(%)": _number(item.get("up_probability")),
                    "기대수익(%)": _number(item.get("expected_return")),
                    "중앙값수익(%)": _number(item.get("median_return")),
                }
            )
    if rows:
        with st.expander("Replay Prediction 상세", expanded=False):
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _selected_case(replay_matches: list[dict[str, Any]], key_prefix: str) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    if not replay_matches:
        return None, None
    options = list(range(min(10, len(replay_matches))))
    selected_index = st.selectbox(
        "비교할 과거 사례",
        options=options,
        format_func=lambda index: f"#{index + 1} {replay_matches[index].get('name') or replay_matches[index].get('ticker') or '-'} · {replay_matches[index].get('event_date') or '-'} · {_classify_case(replay_matches[index])}",
        key=f"{key_prefix}_replay_case",
    )
    return int(selected_index), replay_matches[int(selected_index)]


def _render_selected_workspace(
    conn: sqlite3.Connection,
    current: pd.DataFrame,
    current_label: str,
    selected_index: int,
    match: dict[str, Any],
    key_prefix: str,
    prediction: dict[str, Any],
) -> None:
    pattern = _pattern_for_match(conn, match)
    historical = _pattern_bars(conn, pattern)
    historical_label = str(pattern["name"] or pattern["ticker"]) if pattern is not None else "과거 사례"

    left, right = st.columns([7.2, 2.8], gap="large")
    with left:
        st.markdown("### 원천 데이터 직접 비교")
        st.caption("현재와 과거를 같은 봉 위치로 맞춰 가격·거래량·STO를 한 화면에서 확인합니다.")
        if current.empty or pattern is None or historical.empty:
            st.warning("선택한 Replay 사례에 연결된 과거 원천 봉이 없어 직접 비교 차트를 표시할 수 없습니다.")
            if pattern is None:
                st.caption("Replay 사례 ID와 surge_patterns 연결을 확인해야 합니다.")
            elif historical.empty:
                st.caption("surge_pattern_bars에 해당 pattern_id의 봉 데이터가 필요합니다.")
        else:
            chart = _build_direct_compare_chart(current, historical, current_label, historical_label)
            if chart.data:
                st.plotly_chart(chart, use_container_width=True, config=CHART_CONFIG, key=f"{key_prefix}_verification_workspace_{selected_index}")
            else:
                st.warning("현재/과거 원천 봉의 OHLC 열 구조를 해석하지 못했습니다.")
            with st.expander("간단 Overlay만 보기", expanded=False):
                st.plotly_chart(build_pattern_compare_chart(current, historical, current_label, historical_label), use_container_width=True, config=CHART_CONFIG)
    with right:
        st.markdown("### 검증 패널")
        summary = pd.DataFrame(
            [
                {"항목": "결과 분류", "값": _classify_case(match)},
                {"항목": "주봉 유사도", "값": _format_pct(match.get("weekly_similarity"))},
                {"항목": "STO 유사도", "값": _format_pct(match.get("sto_similarity"))},
                {"항목": "과거 최고수익", "값": _format_pct(match.get("max_return"))},
                {"항목": "과거 최대하락", "값": _format_pct(match.get("max_drawdown"))},
                {"항목": "Prediction", "값": str(prediction.get("grade") or "-")},
            ]
        )
        st.dataframe(summary, hide_index=True, use_container_width=True)
        st.markdown("#### 사람이 확인")
        st.checkbox("가격의 상승·조정 순서가 유사함", key=f"{key_prefix}_check_price_{selected_index}")
        st.checkbox("STO 전환 시점과 방향이 유사함", key=f"{key_prefix}_check_sto_{selected_index}")
        st.checkbox("거래량 확대 시점과 지속성이 유사함", key=f"{key_prefix}_check_volume_{selected_index}")
        st.checkbox("시장·업종·수급 환경 차이를 확인함", key=f"{key_prefix}_check_environment_{selected_index}")
        st.caption("계산값은 참고값입니다. 위 원천 차트와 외부환경 확인 후 주문 여부를 결정합니다.")


def _render_selected_future_path(conn: sqlite3.Connection, match: dict[str, Any]) -> None:
    paths = _future_paths(conn, [match])
    if paths.empty:
        return
    series = paths[paths.columns[0]].dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series.values, mode="lines+markers", name="누적수익률"))
    fig.add_hline(y=0)
    fig.update_layout(height=320, xaxis_title="매칭 이후 거래일", yaxis_title="누적수익률(%)", title="선택 사례의 매칭 이후 20거래일")
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)


def _render_future_distribution(conn: sqlite3.Connection, replay_matches: list[dict[str, Any]]) -> None:
    paths = _future_paths(conn, replay_matches)
    if paths.empty:
        return
    mean_path = paths.mean(axis=1, skipna=True)
    median_path = paths.median(axis=1, skipna=True)
    q25 = paths.quantile(0.25, axis=1)
    q75 = paths.quantile(0.75, axis=1)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=paths.index, y=q75, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=paths.index, y=q25, mode="lines", fill="tonexty", name="25~75% 범위", line=dict(width=0)))
    fig.add_trace(go.Scatter(x=paths.index, y=mean_path, mode="lines+markers", name="평균 경로"))
    fig.add_trace(go.Scatter(x=paths.index, y=median_path, mode="lines", name="중앙값 경로", line=dict(dash="dash")))
    fig.add_hline(y=0)
    fig.update_layout(height=390, xaxis_title="매칭 이후 거래일", yaxis_title="누적수익률(%)", title="유사사례 이후 20거래일 경로 분포")
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)


def render_replay_analysis_panel(*, db_path: str, payload: dict[str, Any], current: pd.DataFrame, current_label: str, key_prefix: str, include_heavy: bool = True) -> None:
    raw_matches = [item for item in (payload.get("replay_matches") or []) if isinstance(item, dict)]
    replay_matches = _dedupe_replay_matches(raw_matches)
    prediction = payload.get("prediction") if isinstance(payload.get("prediction"), dict) else {}
    if len(raw_matches) != len(replay_matches):
        st.caption(f"중복 Replay 사례 {len(raw_matches) - len(replay_matches)}건을 제거했습니다.")

    st.markdown("## 추천 검증 데스크")
    st.caption("알고리즘 계산 결과를 원천 데이터와 직접 대조하고, 유사사례와 환경 차이를 사람이 다시 확인하는 화면입니다.")

    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        availability = _data_availability(conn, current, replay_matches, prediction)
        _render_data_availability(availability)
        _render_replay_overview(replay_matches)
        if not replay_matches:
            st.warning("Replay 사례가 없어 원천 비교를 진행할 수 없습니다.")
            _render_validation_map(replay_matches, prediction)
            _render_prediction(prediction)
            return

        selected_index, match = _selected_case(replay_matches, key_prefix)
        if selected_index is not None and match is not None:
            _render_selected_workspace(conn, current, current_label, selected_index, match, key_prefix, prediction)

        _render_validation_map(replay_matches, prediction)
        _render_outcome_groups(replay_matches)
        _render_prediction(prediction)

        if include_heavy and selected_index is not None and match is not None:
            _render_selected_future_path(conn, match)
            _render_future_distribution(conn, replay_matches)
