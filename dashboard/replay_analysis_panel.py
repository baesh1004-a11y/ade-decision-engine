from __future__ import annotations

import math
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


def _match_ids(match: dict[str, Any]) -> list[str]:
    values = [match.get("source_event_id"), match.get("event_id"), match.get("pattern_id")]
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


def _render_validation_map(replay_matches: list[dict[str, Any]], prediction: dict[str, Any]) -> None:
    st.markdown("### 알고리즘 판단과 원천 증거")
    st.caption("프로그램 계산값과 실제 과거 데이터가 같은 이야기를 하는지 사람이 다시 확인하는 단계입니다.")
    rows = []
    weekly_values = [_number(item.get("weekly_similarity")) for item in replay_matches]
    sto_values = [_number(item.get("sto_similarity")) for item in replay_matches]
    rows.append({"알고리즘 판단": "주봉 패턴 유사도", "계산 결과": _mean_pct(pd.Series(weekly_values)), "사람이 확인할 원천 증거": "현재 주봉과 과거 사례의 가격·거래량 흐름"})
    rows.append({"알고리즘 판단": "STO 유사도", "계산 결과": _mean_pct(pd.Series(sto_values)), "사람이 확인할 원천 증거": "현재와 과거의 STO 방향·전환 시점"})
    rows.append({"알고리즘 판단": "Replay 표본", "계산 결과": f"{len(replay_matches)}건", "사람이 확인할 원천 증거": "매칭 이후 성공·중립·실패 경로"})
    grade = str(prediction.get("grade") or "-") if prediction else "-"
    rows.append({"알고리즘 판단": "Prediction", "계산 결과": grade, "사람이 확인할 원천 증거": "기간별 상승확률·기대수익·경로 분산"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_replay_overview(replay_matches: list[dict[str, Any]]) -> None:
    st.markdown("### 과거 유사사례 성과 요약")
    st.caption("유사도 점수와 실제 사후 결과를 함께 봅니다. 유사도는 닮은 정도일 뿐 결과를 보장하지 않습니다.")
    if not replay_matches:
        st.info("표시할 과거 유사사례가 없습니다.")
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
    metrics = st.columns(6)
    metrics[0].metric("유효 사례", f"{len(frame)}건")
    metrics[1].metric("평균 주봉 유사도", _mean_pct(frame["weekly"]))
    metrics[2].metric("평균 STO 유사도", _mean_pct(frame["sto"]))
    metrics[3].metric("평균 최고수익", _mean_pct(frame["max_return"]))
    metrics[4].metric("과거 사례 중 최대 하락", _format_pct(drawdowns.min() if not drawdowns.empty else None))
    metrics[5].metric("상승 사례 비율", f"{returns.gt(0).mean() * 100:.1f}%" if not returns.empty else "-")

    chart = go.Figure()
    names = [f"#{index} {str(match.get('name') or match.get('ticker') or '사례')}" for index, match in enumerate(replay_matches[:10], start=1)]
    chart.add_trace(go.Bar(name="주봉 유사도", x=names, y=[_number(match.get("weekly_similarity")) for match in replay_matches[:10]]))
    chart.add_trace(go.Bar(name="STO 유사도", x=names, y=[_number(match.get("sto_similarity")) for match in replay_matches[:10]]))
    chart.update_layout(
        barmode="group",
        title="과거 사례별 패턴 유사도 비교",
        xaxis_title="과거 사례",
        yaxis_title="유사도(%)",
        yaxis=dict(range=[0, 100]),
        legend=dict(orientation="h", y=1.12),
        margin=dict(l=20, r=20, t=70, b=20),
        height=390,
    )
    st.plotly_chart(chart, use_container_width=True, config=CHART_CONFIG)
    st.caption("주봉 유사도와 STO 유사도를 함께 보고, 아래 원천 차트에서 실제 모양이 정말 닮았는지 다시 확인합니다.")


def _render_outcome_groups(replay_matches: list[dict[str, Any]]) -> None:
    st.markdown("### 유사사례 결과별 비교")
    st.caption("유사했던 사례를 성공·중립·실패로 나눠, 무엇이 결과를 갈랐는지 확인합니다.")
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
                "현재 대응주차": int(match.get("equivalent_week_index") or 0),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        st.info("결과를 분류할 과거 사례가 없습니다.")
        return
    counts = frame["결과"].value_counts().to_dict()
    cols = st.columns(3)
    for col, label in zip(cols, ["성공", "중립", "실패"]):
        col.metric(label, f"{int(counts.get(label, 0))}건")
    tabs = st.tabs(["성공 사례", "중립 사례", "실패 사례"])
    for tab, label in zip(tabs, ["성공", "중립", "실패"]):
        with tab:
            subset = frame[frame["결과"] == label]
            if subset.empty:
                st.caption(f"{label}로 분류된 사례가 없습니다.")
            else:
                st.dataframe(subset, hide_index=True, use_container_width=True)
    st.caption("현재 분류는 저장된 사후수익·최대상승·최대하락 값으로 계산합니다. 향후 5·10·20일 수익이 저장되면 기준을 더 정교하게 확장할 수 있습니다.")


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
        st.info("Prediction 데이터가 아직 없습니다. 새 추천 실행 후 다중 기간 확률·수익 분석이 생성됩니다.")
        return
    frame = pd.DataFrame(rows)
    st.dataframe(frame, hide_index=True, use_container_width=True)
    fig = go.Figure()
    days = [int(str(item["기간"]).replace("일", "")) for item in rows]
    fig.add_trace(go.Scatter(x=days, y=[item["상승확률(%)"] for item in rows], mode="lines+markers", name="상승확률", yaxis="y1"))
    fig.add_trace(go.Scatter(x=days, y=[item["기대수익(%)"] for item in rows], mode="lines+markers", name="기대수익", yaxis="y2"))
    fig.add_trace(go.Scatter(x=days, y=[item["중앙값수익(%)"] for item in rows], mode="lines+markers", name="중앙값수익", yaxis="y2"))
    fig.update_layout(
        title="기간별 확률·기대수익 곡선",
        xaxis_title="거래일",
        yaxis=dict(title="상승확률(%)", range=[0, 100]),
        yaxis2=dict(title="수익률(%)", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.12),
        margin=dict(l=20, r=20, t=70, b=20),
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
    summary = st.columns(6)
    summary[0].metric("예측등급", str(prediction.get("grade") or "-"))
    summary[1].metric("표본수", f"{int(prediction.get('sample_count') or 0)}건")
    summary[2].metric("7일 최대수익", _format_pct(prediction.get("expected_max_return_7d")))
    summary[3].metric("20일 최대수익", _format_pct(prediction.get("expected_max_return_20d")))
    summary[4].metric("7일 최대낙폭", _format_pct(prediction.get("expected_mdd_7d")))
    peak_day = _number(prediction.get("expected_peak_day"))
    summary[5].metric("예상 고점", f"{peak_day:.1f}일" if peak_day is not None else "-")


def _render_replay_table(replay_matches: list[dict[str, Any]]) -> None:
    st.markdown("### 과거 유사사례 Top N")
    rows = []
    for index, match in enumerate(replay_matches[:10], start=1):
        rows.append(
            {
                "순위": index,
                "종목": match.get("name") or match.get("ticker") or "-",
                "기준일": match.get("event_date") or "-",
                "결과": _classify_case(match),
                "주봉유사도(%)": _number(match.get("weekly_similarity")),
                "STO유사도(%)": _number(match.get("sto_similarity")),
                "최고수익(%)": _number(match.get("max_return")),
                "최대하락(%)": _number(match.get("max_drawdown")),
                "현재 대응주차": int(match.get("equivalent_week_index") or 0),
                "비교주수": int(match.get("weeks_compared") or 0),
                "향후주수": int(match.get("future_weeks_available") or 0),
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("표시할 과거 유사사례가 없습니다.")


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


def _render_selected_compare(conn: sqlite3.Connection, current: pd.DataFrame, current_label: str, selected_index: int, match: dict[str, Any], key_prefix: str) -> None:
    st.markdown("### 계산값 검증: 현재 종목 vs 선택 과거 사례")
    st.caption("점수만 보지 말고 가격·거래량·STO의 실제 흐름이 정말 닮았는지 확인합니다. 매칭 이후 성과는 아래 별도 차트에서 봅니다.")
    pattern = _pattern_for_match(conn, match)
    historical = _pattern_bars(conn, pattern)
    details = st.columns(6)
    details[0].metric("주봉 유사도", _format_pct(match.get("weekly_similarity")))
    details[1].metric("STO 유사도", _format_pct(match.get("sto_similarity")))
    details[2].metric("과거 최고수익", _format_pct(match.get("max_return")))
    details[3].metric("과거 최대하락", _format_pct(match.get("max_drawdown")))
    details[4].metric("현재 대응", f"{int(match.get('equivalent_week_index') or 0)}주차")
    details[5].metric("비교 구간", f"{int(match.get('weeks_compared') or 0)}주")
    if current.empty or pattern is None or historical.empty:
        st.warning("선택 사례의 원본 봉 데이터를 찾지 못해 비교 차트를 표시할 수 없습니다.")
        return
    historical_label = str(pattern["name"] or pattern["ticker"])
    st.plotly_chart(
        build_pattern_compare_chart(current, historical, current_label, historical_label),
        use_container_width=True,
        config=CHART_CONFIG,
        key=f"{key_prefix}_replay_compare_{selected_index}",
    )
    st.markdown("**사람이 확인할 항목**")
    st.write("- 상승·조정의 순서가 실제로 같은가")
    st.write("- 거래량이 확대되는 시점이 비슷한가")
    st.write("- STO가 방향을 바꾸는 시점이 일치하는가")
    st.write("- 현재 종목만의 비정상 급등·급락이 섞여 있지 않은가")


def _render_selected_future_path(conn: sqlite3.Connection, match: dict[str, Any]) -> None:
    st.markdown("### 선택 사례의 매칭 이후 20거래일")
    paths = _future_paths(conn, [match])
    if paths.empty:
        st.caption("선택 사례의 미래 경로 원본이 없습니다. Replay 원본 데이터 재생성이 필요합니다.")
        return
    column = paths.columns[0]
    series = paths[column].dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series.values, mode="lines+markers", name=str(column)))
    fig.add_hline(y=0)
    fig.add_hline(y=10, line_dash="dot", annotation_text="+10%")
    fig.add_hline(y=-10, line_dash="dot", annotation_text="-10%")
    fig.update_layout(
        title="선택 사례 매칭 이후 누적수익률",
        xaxis_title="매칭 이후 거래일",
        yaxis_title="누적수익률(%)",
        margin=dict(l=20, r=20, t=70, b=20),
        height=370,
    )
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
    path_metrics = st.columns(4)
    path_metrics[0].metric("최종수익", f"{series.iloc[-1]:+.2f}%")
    path_metrics[1].metric("최대상승", f"{series.max():+.2f}%")
    path_metrics[2].metric("최대하락", f"{series.min():+.2f}%")
    path_metrics[3].metric("고점 도달일", f"{int(series.idxmax())}일")


def _render_future_distribution(conn: sqlite3.Connection, replay_matches: list[dict[str, Any]]) -> None:
    st.markdown("### 유사사례 이후 20거래일 경로 분포")
    paths = _future_paths(conn, replay_matches)
    if paths.empty:
        st.info("미래 경로 원본이 없어 분포 차트를 생성하지 못했습니다. Replay 이벤트 흐름 데이터 재생성이 필요합니다.")
        return
    mean_path = paths.mean(axis=1, skipna=True)
    median_path = paths.median(axis=1, skipna=True)
    q25 = paths.quantile(0.25, axis=1)
    q75 = paths.quantile(0.75, axis=1)
    min_path = paths.min(axis=1, skipna=True)
    max_path = paths.max(axis=1, skipna=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=paths.index, y=q75, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=paths.index, y=q25, mode="lines", fill="tonexty", name="25~75% 범위", line=dict(width=0)))
    for column in paths.columns:
        fig.add_trace(go.Scatter(x=paths.index, y=paths[column], mode="lines", name=str(column), opacity=0.22, line=dict(width=1), showlegend=False))
    fig.add_trace(go.Scatter(x=paths.index, y=mean_path, mode="lines+markers", name="평균 경로", line=dict(width=4)))
    fig.add_trace(go.Scatter(x=paths.index, y=median_path, mode="lines", name="중앙값 경로", line=dict(width=3, dash="dash")))
    fig.add_trace(go.Scatter(x=paths.index, y=max_path, mode="lines", name="최고 경로", line=dict(width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=paths.index, y=min_path, mode="lines", name="최저 경로", line=dict(width=1, dash="dot")))
    fig.add_hline(y=0)
    fig.add_hline(y=10, line_dash="dot", annotation_text="+10%")
    fig.add_hline(y=-10, line_dash="dot", annotation_text="-10%")
    fig.update_layout(
        title="과거 유사사례의 매칭 이후 경로 분포",
        xaxis_title="매칭 이후 거래일",
        yaxis_title="누적수익률(%)",
        legend=dict(orientation="h", y=1.12),
        margin=dict(l=20, r=20, t=80, b=20),
        height=500,
    )
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    full20 = paths.iloc[20].dropna() if len(paths.index) > 20 else pd.Series(dtype=float)
    last_valid = paths.apply(lambda series: series.dropna().iloc[-1] if not series.dropna().empty else None).dropna()
    stats_source = full20 if not full20.empty else last_valid
    stat_cols = st.columns(6)
    stat_cols[0].metric("전체 경로", f"{len(paths.columns)}건")
    stat_cols[1].metric("20일 완전 표본", f"{len(full20)}건")
    stat_cols[2].metric("평균수익", f"{stats_source.mean():+.2f}%" if not stats_source.empty else "-")
    stat_cols[3].metric("중앙값", f"{stats_source.median():+.2f}%" if not stats_source.empty else "-")
    stat_cols[4].metric("상승확률", f"{stats_source.gt(0).mean() * 100:.1f}%" if not stats_source.empty else "-")
    stat_cols[5].metric("손익비", f"{abs(stats_source[stats_source > 0].mean() / stats_source[stats_source < 0].mean()):.2f}" if (stats_source.gt(0).any() and stats_source.lt(0).any()) else "-")

    interpretation = []
    if not stats_source.empty:
        interpretation.append(f"표본 {len(stats_source)}건 기준 평균수익은 {stats_source.mean():+.2f}%, 중앙값은 {stats_source.median():+.2f}%입니다.")
        interpretation.append(f"상승 사례 비율은 {stats_source.gt(0).mean() * 100:.1f}%이며 최고·최저 결과는 {stats_source.max():+.2f}% / {stats_source.min():+.2f}%입니다.")
        if stats_source.mean() > 0 and stats_source.median() > 0:
            interpretation.append("평균과 중앙값이 모두 양수여서 과거 경로의 중심은 상승 쪽에 있습니다.")
        elif stats_source.mean() > 0 >= stats_source.median():
            interpretation.append("일부 강한 상승 사례가 평균을 끌어올린 구조로, 사례 간 편차가 큽니다.")
        else:
            interpretation.append("과거 경로 중심이 보수적이므로 기대수익보다 하방 리스크 관리가 우선입니다.")
    st.markdown("#### 정량 해석")
    for sentence in interpretation:
        st.write(f"- {sentence}")


def render_replay_analysis_panel(*, db_path: str, payload: dict[str, Any], current: pd.DataFrame, current_label: str, key_prefix: str, include_heavy: bool = True) -> None:
    raw_matches = [item for item in (payload.get("replay_matches") or []) if isinstance(item, dict)]
    replay_matches = _dedupe_replay_matches(raw_matches)
    prediction = payload.get("prediction") if isinstance(payload.get("prediction"), dict) else {}
    if len(raw_matches) != len(replay_matches):
        st.caption(f"중복 Replay 사례 {len(raw_matches) - len(replay_matches)}건을 제거했습니다.")
    _render_validation_map(replay_matches, prediction)
    _render_replay_overview(replay_matches)
    _render_outcome_groups(replay_matches)
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
        _render_selected_future_path(conn, match)
        _render_future_distribution(conn, replay_matches)
