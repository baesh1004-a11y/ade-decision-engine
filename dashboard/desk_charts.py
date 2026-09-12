"""Evidence charts use a shared observation axis and retain the engine's STO curves."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from sto.structure_similarity import STOStructureSimilarityEngine

CURRENT = "#1D4ED8"
HISTORICAL = "#19A6A0"


def _theme(fig: go.Figure, height: int = 440) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 12, "r": 18, "t": 35, "b": 18},
        hovermode="x unified",
        font={
            "family": "Inter, Apple SD Gothic Neo, Malgun Gothic, sans-serif",
            "size": 13,
            "color": "#50647C",
        },
        legend={"orientation": "h", "y": 1.12, "x": 0, "font": {"size": 13}},
        hoverlabel={"bgcolor": "#FFFFFF", "font": {"color": "#13253E", "size": 14}},
    )
    fig.update_xaxes(showgrid=False, zeroline=False, title_font={"size": 13})
    fig.update_yaxes(gridcolor="#EAF0F7", zeroline=False, title_font={"size": 13})
    return fig


def compare_prices(current: pd.DataFrame, historical: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.76, 0.24],
        vertical_spacing=0.1,
    )
    for frame, label, color in [
        (current, "현재 · 추천 시점", CURRENT),
        (historical, "과거 · 급등 직전", HISTORICAL),
    ]:
        if frame.empty or len(frame) < 120:
            continue
        data = frame.tail(120).reset_index(drop=True)
        close = pd.to_numeric(data["Close"], errors="coerce")
        if close.isna().any() or (close <= 0).any():
            continue
        x = list(range(-119, 1))
        fig.add_trace(
            go.Scatter(
                x=x,
                y=close / close.iloc[0] * 100,
                name=label,
                line={"color": color, "width": 2.6},
                customdata=data["Date"].astype(str),
                hovertemplate="%{customdata}<br>기준가 100 대비 %{y:.2f}<extra>%{fullData.name}</extra>",
            ),
            row=1,
            col=1,
        )
        volume = pd.to_numeric(data["Volume"], errors="coerce")
        mean = volume.mean()
        if pd.notna(mean) and mean > 0:
            fig.add_trace(
                go.Bar(
                    x=x,
                    y=volume / mean,
                    name=label + " 거래량",
                    marker_color=color,
                    opacity=0.3,
                    showlegend=False,
                ),
                row=2,
                col=1,
            )
    fig.update_yaxes(title_text="기준가 100", row=1, col=1)
    fig.update_yaxes(title_text="거래량 배수", row=2, col=1)
    fig.update_xaxes(title_text="비교 기준일까지의 거래일", row=2, col=1)
    fig.add_vline(x=0, line_color="#8CA1BA", line_dash="dot")
    return _theme(fig)


def compare_sto(current: pd.DataFrame, historical: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("단기 5·3·3", "중기 10·6·6", "장기 20·12·12"),
    )
    engine = STOStructureSimilarityEngine()
    for frame, label, color in [
        (current, "현재", CURRENT),
        (historical, "과거", HISTORICAL),
    ]:
        if len(frame) < 120:
            continue
        structure = engine.extract(frame.tail(120))
        for index, values in enumerate(
            [structure.short_path, structure.middle_path, structure.long_path], 1
        ):
            fig.add_trace(
                go.Scatter(
                    x=list(range(-len(values) + 1, 1)),
                    y=[v * 100 for v in values],
                    name=label,
                    legendgroup=label,
                    showlegend=index == 1,
                    line={"color": color, "width": 2.5},
                ),
                row=index,
                col=1,
            )
            fig.update_yaxes(range=[0, 100], tickvals=[20, 50, 80], row=index, col=1)
    fig.update_xaxes(title_text="비교 기준 주까지의 주차", row=3, col=1)
    return _theme(fig, 460)
