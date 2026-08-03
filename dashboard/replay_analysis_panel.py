from __future__ import annotations

import sqlite3
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.charts import CHART_CONFIG, build_pattern_compare_chart


def _number(value: object) -> float | None:
    try:
        if value is None or str(value) == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _match_ids(match: dict[str, Any]) -> list[str]:
    values = [
        match.get("source_event_id"),
        match.get("event_id"),
        match.get("pattern_id"),
    ]
    return [str(value).strip() for value in values if str(value or "").strip()]


def _pattern_for_match(conn: sqlite3.Connection, match: dict[str, Any]):
    if not _table_exists(conn, "surge_patterns"):
        return None
    for event_id in _match_ids(match):
        for column in ("source_event_id", "pattern_id"):
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


def _render_prediction(prediction: dict[str, Any]) -> None:
    st.markdown("### 전체 사례 종합 Replay Prediction")
    horizons = prediction.get("horizons") or []
    rows = []
    for item in horizons:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "기간": f"{int(item.get('days') or 0)}일",
                "표본": int(item.get("sample_count") or 0),
                "상승확률(%)": _number(item.get("up_probability")),
                "기대수익(%)": _number(item.get("expected_return")),
                "중앙값수익(%)": _number(item.get("median_return")),
            }
        )
    if not rows:
        st.info("다중 기간 예측 데이터가 없습니다. 다음 추천 실행부터 생성됩니다.")
        return
    frame = pd.DataFrame(rows)
    st.dataframe(frame, hide_index=True, use_container_width=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[int(str(item["기간"]).replace("일", "")) for item in rows], y=[item["상승확률(%)"] for item in rows], mode="lines+markers", name="상승확률", yaxis="y1"))
    fig.add_trace(go.Scatter(x=[int(str(item["기간"]).replace("일", "")) for item in rows], y=[item["기대수익(%)"] for item in rows], mode="lines+markers", name="기대수익", yaxis="y2"))
    fig.update_layout(xaxis_title="거래일", yaxis=dict(title="상승확률(%)", range=[0, 100]), yaxis2=dict(title="기대수익(%)", overlaying="y", side="right"), legend=dict(orientation="h"), margin=dict(l=10, r=10, t=30, b=10), height=360)
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
    summary = st.columns(6)
    summary[0].metric("예측등급", str(prediction.get("grade") or "-"))
    summary[1].metric("표본수", f"{int(prediction.get('sample_count') or 0)}건")
    summary[2].metric("7일 최대수익", f"{float(prediction.get('expected_max_return_7d') or 0):+.2f}%")
    summary[3].metric("20일 최대수익", f"{float(prediction.get('expected_max_return_20d') or 0):+.2f}%")
    summary[4].metric("7일 최대낙폭", f"{float(prediction.get('expected_mdd_7d') or 0):+.2f}%")
    summary[5].metric("예상 고점", f"{float(prediction.get('expected_peak_day') or 0):.1f}일")


def _render_replay_table(replay_matches: list[dict[str, Any]]) -> None:
    st.markdown("### Replay 유사사례 Top N")
    rows = []
    for index, match in enumerate(replay_matches[:10], start=1):
        rows.append({"순위": index, "종목": match.get("name") or match.get("ticker") or "-", "기준일": match.get("event_date") or "-", "주봉유사도(%)": _number(match.get("weekly_similarity")), "STO유사도(%)": _number(match.get("sto_similarity")), "최대상승(%)": _number(match.get("max_return")), "최대낙폭(%)": _number(match.get("max_drawdown")), "대응주차": int(match.get("equivalent_week_index") or 0), "비교주수": int(match.get("weeks_compared") or 0), "향후주수": int(match.get("future_weeks_available") or 0)})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("표시할 Replay 사례가 없습니다.")


def _selected_case(replay_matches: list[dict[str, Any]], key_prefix: str) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    if not replay_matches:
        return None, None
    options = list(range(min(10, len(replay_matches))))
    selected_index = st.selectbox(
        "비교할 Replay 사례",
        options=options,
        format_func=lambda index: f"#{index + 1} {replay_matches[index].get('name') or replay_matches[index].get('ticker') or '-'} · {replay_matches[index].get('event_date') or '-'}",
        key=f"{key_prefix}_replay_case",
    )
    return int(selected_index), replay_matches[int(selected_index)]


def _render_selected_compare(conn: sqlite3.Connection, current: pd.DataFrame, current_label: str, selected_index: int, match: dict[str, Any], key_prefix: str) -> None:
    st.markdown("### 선택 Replay 사례 분석")
    pattern = _pattern_for_match(conn, match)
    historical = _pattern_bars(conn, pattern)
    details = st.columns(5)
    details[0].metric("주봉 유사도", f"{float(match.get('weekly_similarity') or 0):.2f}%")
    details[1].metric("STO 유사도", f"{float(match.get('sto_similarity') or 0):.2f}%")
    details[2].metric("현재 대응", f"{int(match.get('equivalent_week_index') or 0)}주차")
    details[3].metric("비교 구간", f"{int(match.get('weeks_compared') or 0)}주")
    details[4].metric("향후 확인", f"{int(match.get('future_weeks_available') or 0)}주")
    if current.empty or pattern is None or historical.empty:
        st.caption("선택한 사례의 저장 차트 데이터를 찾지 못했습니다.")
        return
    historical_label = str(pattern["name"] or pattern["ticker"])
    st.plotly_chart(build_pattern_compare_chart(current, historical, current_label, historical_label), use_container_width=True, config=CHART_CONFIG, key=f"{key_prefix}_replay_compare_{selected_index}")


def _render_selected_future_path(conn: sqlite3.Connection, match: dict[str, Any]) -> None:
    paths = _future_paths(conn, [match])
    if paths.empty:
        st.caption("선택 사례의 미래 경로 원본이 없습니다.")
        return
    column = paths.columns[0]
    fig = go.Figure(go.Scatter(x=paths.index, y=paths[column], mode="lines+markers", name=str(column)))
    fig.add_hline(y=0)
    fig.update_layout(xaxis_title="매칭 이후 거래일", yaxis_title="누적수익률(%)", margin=dict(l=10, r=10, t=30, b=10), height=330)
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)


def _render_future_distribution(conn: sqlite3.Connection, replay_matches: list[dict[str, Any]]) -> None:
    st.markdown("### 전체 Top N 미래 20거래일 경로 분포")
    paths = _future_paths(conn, replay_matches)
    if paths.empty:
        st.info("미래 경로 원본이 없어 분포 차트를 생성하지 못했습니다.")
        return
    fig = go.Figure()
    for column in paths.columns:
        fig.add_trace(go.Scatter(x=paths.index, y=paths[column], mode="lines", name=str(column), opacity=0.35))
    mean_path = paths.mean(axis=1, skipna=True)
    median_path = paths.median(axis=1, skipna=True)
    min_path = paths.min(axis=1, skipna=True)
    max_path = paths.max(axis=1, skipna=True)
    fig.add_trace(go.Scatter(x=paths.index, y=mean_path, mode="lines+markers", name="평균 경로", line=dict(width=4)))
    fig.add_trace(go.Scatter(x=paths.index, y=median_path, mode="lines", name="중앙값 경로", line=dict(width=3, dash="dash")))
    fig.add_trace(go.Scatter(x=paths.index, y=max_path, mode="lines", name="최고 범위", line=dict(width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=paths.index, y=min_path, mode="lines", name="최저 범위", line=dict(width=1, dash="dot")))
    fig.add_hline(y=0)
    fig.update_layout(xaxis_title="매칭 이후 거래일", yaxis_title="누적수익률(%)", legend=dict(orientation="h"), margin=dict(l=10, r=10, t=30, b=10), height=440)
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    full20 = paths.iloc[20].dropna() if len(paths.index) > 20 else pd.Series(dtype=float)
    last_valid = paths.apply(lambda series: series.dropna().iloc[-1] if not series.dropna().empty else None).dropna()
    rows = [{"지표": "전체 경로", "값": f"{len(paths.columns)}건"}, {"지표": "20일 완전 표본", "값": f"{len(full20)}건"}]
    if not full20.empty:
        rows.extend([
            {"지표": "20일 평균수익", "값": f"{full20.mean():+.2f}%"},
            {"지표": "20일 중앙값", "값": f"{full20.median():+.2f}%"},
            {"지표": "20일 최고 사례", "값": f"{full20.max():+.2f}%"},
            {"지표": "20일 최저 사례", "값": f"{full20.min():+.2f}%"},
            {"지표": "20일 상승 사례 비율", "값": f"{(full20.gt(0).mean() * 100):.1f}%"},
        ])
    if len(last_valid) > len(full20):
        rows.extend([
            {"지표": "마지막 확보일 참고 표본", "값": f"{len(last_valid)}건"},
            {"지표": "마지막 확보일 평균", "값": f"{last_valid.mean():+.2f}%"},
        ])
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_replay_analysis_panel(*, db_path: str, payload: dict[str, Any], current: pd.DataFrame, current_label: str, key_prefix: str, include_heavy: bool = True) -> None:
    replay_matches = [item for item in (payload.get("replay_matches") or []) if isinstance(item, dict)]
    prediction = payload.get("prediction") if isinstance(payload.get("prediction"), dict) else {}
    _render_replay_table(replay_matches)
    _render_prediction(prediction)
    if not replay_matches:
        return
    selected_index, match = _selected_case(replay_matches, key_prefix)
    if selected_index is None or match is None:
        return
    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        _render_selected_compare(conn, current, current_label, selected_index, match, key_prefix)
        if include_heavy:
            _render_selected_future_path(conn, match)
            _render_future_distribution(conn, replay_matches)
