from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from sto.structure_similarity import STOStructure, STOStructureSimilarityEngine


def _safe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _rename_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    renamed = frame.rename(
        columns={
            "trade_date": "Date",
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    ).copy()
    if "Date" in renamed.columns:
        renamed["Date"] = pd.to_datetime(renamed["Date"], errors="coerce")
    return renamed


def _historical_structure(engine: STOStructureSimilarityEngine, pattern: Any, historical: pd.DataFrame) -> STOStructure | None:
    raw = _safe_json(pattern["sto_json"] if pattern is not None and "sto_json" in pattern.keys() else None)
    if raw:
        allowed = STOStructure.__dataclass_fields__.keys()
        values = {key: raw[key] for key in allowed if key in raw}
        try:
            return STOStructure(**values)
        except TypeError:
            pass
    normalized = _rename_ohlcv(historical)
    if normalized.empty:
        return None
    return engine.extract(normalized)


def _layer_similarity(engine: STOStructureSimilarityEngine, current_path: Any, historical_path: Any, current_value: float, historical_value: float) -> float:
    if current_path and historical_path and len(current_path) == len(historical_path):
        return round(engine._path_similarity(list(current_path), list(historical_path)), 2)
    distance = abs(float(current_value) - float(historical_value)) / 100.0
    return round(max(0.0, 100.0 / (1.0 + distance * 5.0)), 2)


def _signal_similarity(engine: STOStructureSimilarityEngine, current: STOStructure, historical: STOStructure) -> float:
    if current.arrangement == historical.arrangement:
        arrangement = 100.0
    elif engine._compatible(current.arrangement, historical.arrangement):
        arrangement = 55.0
    else:
        arrangement = 25.0
    structure = engine._feature_similarity(current.vector[3:6], historical.vector[3:6], scale=3.0)
    slope = engine._feature_similarity(current.vector[6:9], historical.vector[6:9], scale=6.0)
    return round(arrangement * 0.45 + structure * 0.30 + slope * 0.25, 2)


def _status(score: float) -> tuple[str, str]:
    if score >= 90:
        return "매우 유사", "추세 구조와 모멘텀 배열이 거의 동일"
    if score >= 80:
        return "유사", "핵심 흐름은 유사하나 일부 속도 차이 존재"
    if score >= 65:
        return "부분 유사", "방향은 비슷하지만 계층 간 배열 차이 존재"
    return "낮은 유사", "현재 구조와 과거 급등 직전 구조의 차이가 큼"


def _path_frame(structure: STOStructure, label: str) -> pd.DataFrame:
    paths = {
        "단기": list(structure.short_path or []),
        "중기": list(structure.middle_path or []),
        "장기": list(structure.long_path or []),
    }
    max_len = max((len(v) for v in paths.values()), default=0)
    if max_len == 0:
        return pd.DataFrame()
    data: list[dict[str, Any]] = []
    for layer, values in paths.items():
        for index, value in enumerate(values):
            data.append({"구간": index + 1, "계층": layer, "값": float(value), "대상": label})
    return pd.DataFrame(data)


def build_sto_trajectory_figure(current: STOStructure, historical: STOStructure, current_label: str, historical_label: str) -> go.Figure:
    current_frame = _path_frame(current, current_label)
    historical_frame = _path_frame(historical, historical_label)
    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("단기 STO", "중기 STO", "장기 STO"),
    )
    layer_to_row = {"단기": 1, "중기": 2, "장기": 3}
    for frame, dash in ((historical_frame, "dash"), (current_frame, "solid")):
        if frame.empty:
            continue
        for layer, row_no in layer_to_row.items():
            layer_frame = frame[frame["계층"] == layer]
            if layer_frame.empty:
                continue
            target = str(layer_frame["대상"].iloc[0])
            figure.add_trace(
                go.Scatter(
                    x=layer_frame["구간"],
                    y=layer_frame["값"],
                    mode="lines+markers",
                    name=f"{target} · {layer}",
                    line={"dash": dash},
                    hovertemplate="구간 %{x}<br>STO %{y:.2f}<extra>%{fullData.name}</extra>",
                ),
                row=row_no,
                col=1,
            )
    for row_no in (1, 2, 3):
        figure.add_hrect(y0=80, y1=100, line_width=0, opacity=0.06, row=row_no, col=1)
        figure.add_hrect(y0=0, y1=20, line_width=0, opacity=0.06, row=row_no, col=1)
        figure.update_yaxes(range=[0, 100], title_text="STO", row=row_no, col=1)
    figure.update_xaxes(title_text="최근 비교 구간", row=3, col=1)
    figure.update_layout(
        height=760,
        margin={"l": 45, "r": 20, "t": 70, "b": 45},
        legend={"orientation": "h", "y": 1.08},
        hovermode="x unified",
        title="현재 종목과 과거 급등 직전 STO 궤적 비교",
    )
    return figure


def _normalize_close(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = _rename_ohlcv(frame)
    if normalized.empty or "Close" not in normalized.columns:
        return pd.DataFrame()
    result = normalized[[column for column in ("Date", "Close", "Volume") if column in normalized.columns]].copy()
    result = result.dropna(subset=["Close"])
    if result.empty:
        return pd.DataFrame()
    base = float(result["Close"].iloc[0])
    if base <= 0:
        return pd.DataFrame()
    result["NormalizedClose"] = result["Close"].astype(float) / base * 100.0
    result["Sequence"] = range(1, len(result) + 1)
    return result


def build_price_comparison_figure(current: pd.DataFrame, historical: pd.DataFrame, current_label: str, historical_label: str) -> go.Figure:
    current_norm = _normalize_close(current)
    historical_norm = _normalize_close(historical)
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.72, 0.28])
    for frame, label, dash in ((historical_norm, historical_label, "dash"), (current_norm, current_label, "solid")):
        if frame.empty:
            continue
        figure.add_trace(
            go.Scatter(
                x=frame["Sequence"],
                y=frame["NormalizedClose"],
                mode="lines",
                name=f"{label} 정규화 가격",
                line={"dash": dash, "width": 2.4},
                hovertemplate="구간 %{x}<br>기준 대비 %{y:.2f}<extra>%{fullData.name}</extra>",
            ),
            row=1,
            col=1,
        )
        if "Volume" in frame.columns:
            figure.add_trace(
                go.Bar(
                    x=frame["Sequence"],
                    y=frame["Volume"],
                    name=f"{label} 거래량",
                    opacity=0.45,
                    hovertemplate="구간 %{x}<br>거래량 %{y:,.0f}<extra>%{fullData.name}</extra>",
                ),
                row=2,
                col=1,
            )
    figure.add_hline(y=100, line_dash="dot", row=1, col=1)
    figure.update_yaxes(title_text="기준=100", row=1, col=1)
    figure.update_yaxes(title_text="거래량", row=2, col=1)
    figure.update_xaxes(title_text="정렬된 비교 구간", row=2, col=1)
    figure.update_layout(
        height=640,
        margin={"l": 45, "r": 20, "t": 70, "b": 45},
        legend={"orientation": "h", "y": 1.08},
        hovermode="x unified",
        barmode="overlay",
        title="현재 추천종목과 과거 유사사례의 정규화 가격·거래량 비교",
    )
    return figure


def _analysis_rows(current: STOStructure, historical: STOStructure, scores: dict[str, float]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    values = (
        ("단기 STO", current.short, historical.short, scores["단기 STO"]),
        ("중기 STO", current.middle, historical.middle, scores["중기 STO"]),
        ("장기 STO", current.long, historical.long, scores["장기 STO"]),
    )
    for label, current_value, historical_value, score in values:
        state, interpretation = _status(score)
        rows.append(
            {
                "계층": label,
                "현재": f"{float(current_value):.1f}",
                "과거": f"{float(historical_value):.1f}",
                "유사도": f"{score:.1f}%",
                "판정": state,
                "해석": interpretation,
            }
        )
    signal_state, signal_note = _status(scores["Signal"])
    rows.append(
        {
            "계층": "Signal",
            "현재": str(current.arrangement),
            "과거": str(historical.arrangement),
            "유사도": f"{scores['Signal']:.1f}%",
            "판정": signal_state,
            "해석": signal_note,
        }
    )
    return rows


def render_professional_sto_panel(
    *,
    current: pd.DataFrame,
    historical: pd.DataFrame,
    pattern: Any,
    current_label: str,
    historical_label: str,
    stored_similarity: float | None = None,
) -> None:
    import streamlit as st

    normalized_current = _rename_ohlcv(current)
    normalized_historical = _rename_ohlcv(historical)
    if normalized_current.empty or pattern is None:
        st.info("STO 구조 분석에 필요한 현재 가격 또는 과거 패턴 데이터가 부족합니다.")
        return

    engine = STOStructureSimilarityEngine()
    try:
        current_structure = engine.extract(normalized_current)
        historical_structure = _historical_structure(engine, pattern, normalized_historical)
    except Exception:
        st.info("STO 구조를 계산하지 못했습니다. 가격 데이터 구조를 확인해 주세요.")
        return
    if historical_structure is None:
        st.info("과거 유사사례의 STO 구조 데이터가 없습니다.")
        return

    scores = {
        "단기 STO": _layer_similarity(engine, current_structure.short_path, historical_structure.short_path, current_structure.short, historical_structure.short),
        "중기 STO": _layer_similarity(engine, current_structure.middle_path, historical_structure.middle_path, current_structure.middle, historical_structure.middle),
        "장기 STO": _layer_similarity(engine, current_structure.long_path, historical_structure.long_path, current_structure.long, historical_structure.long),
        "Signal": _signal_similarity(engine, current_structure, historical_structure),
    }

    st.markdown("### STO 구조 유사도 분석")
    st.caption("단기·중기·장기 STO의 절대 수준보다 최근 궤적, 계층 배열, 방향성과 기울기의 일치도를 함께 평가합니다.")
    columns = st.columns(4)
    for column, (label, score) in zip(columns, scores.items()):
        state, _ = _status(score)
        column.metric(label, f"{score:.1f}%", state)
    if stored_similarity is not None:
        calculated = sum(scores.values()) / len(scores)
        st.caption(f"저장된 종합 STO 유사도 {stored_similarity:.1f}% · 화면 재계산 평균 {calculated:.1f}% · 산식과 저장 시점 차이로 값이 다를 수 있습니다.")

    st.dataframe(_analysis_rows(current_structure, historical_structure, scores), hide_index=True, use_container_width=True)

    st.plotly_chart(
        build_sto_trajectory_figure(current_structure, historical_structure, current_label, historical_label),
        use_container_width=True,
        config={"displaylogo": False, "responsive": True},
    )
    st.plotly_chart(
        build_price_comparison_figure(normalized_current, normalized_historical, current_label, historical_label),
        use_container_width=True,
        config={"displaylogo": False, "responsive": True},
    )

    similarities = list(scores.values())
    weakest = min(scores, key=scores.get)
    strongest = max(scores, key=scores.get)
    if min(similarities) >= 80:
        headline = "세 계층과 Signal이 모두 높은 수준으로 일치합니다."
    elif scores["장기 STO"] >= 80 and scores["단기 STO"] < 65:
        headline = "장기 구조는 유사하지만 단기 진입 타이밍은 과거 사례와 다릅니다."
    elif scores["Signal"] < 65:
        headline = "STO 절대값보다 계층 배열과 방향성이 과거 사례와 다릅니다."
    else:
        headline = "일부 계층만 유사하므로 선택적 참고가 필요합니다."
    st.markdown("#### 전문가 해석")
    st.write(headline)
    st.caption(
        f"가장 유사한 요소는 {strongest}({scores[strongest]:.1f}%), 가장 차이가 큰 요소는 {weakest}({scores[weakest]:.1f}%)입니다. "
        "유사도는 과거 수익의 재현 가능성을 보장하지 않으며, 가격·거래량·시장 환경과 함께 해석해야 합니다."
    )
