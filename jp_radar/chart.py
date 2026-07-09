from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from jp_radar.engine import RadarResult, TimeframeRadarResult


ENERGY_LINES = [
    ("빨", "s_k", "red"),
    ("주", "s_d", "orange"),
    ("노", "m_k", "yellow"),
    ("초", "m_d", "green"),
    ("파", "l_k", "blue"),
    ("남", "l_d", "purple"),
]


def make_radar_chart(result: RadarResult) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=2,
        shared_xaxes="columns",
        vertical_spacing=0.08,
        horizontal_spacing=0.05,
        specs=[[{"secondary_y": True}, {"secondary_y": True}], [{"secondary_y": False}, {"secondary_y": False}]],
        subplot_titles=(
            "일봉 Daily · 지수 및 에너지",
            "주봉 Weekly · 지수 및 에너지",
            "일봉 Daily · MACD",
            "주봉 Weekly · MACD",
        ),
    )
    _add_timeframe(fig, result.daily, "D", row=1, col=1, macd_row=2, macd_col=1)
    _add_timeframe(fig, result.weekly, "W", row=1, col=2, macd_row=2, macd_col=2)
    for col in [1, 2]:
        fig.add_hline(y=2, line_dash="dash", line_color="lime", line_width=2, opacity=0.5, row=1, col=col, secondary_y=False)
        fig.add_hline(y=8, line_dash="dash", line_color="red", line_width=2, opacity=0.5, row=1, col=col, secondary_y=False)
    fig.update_layout(
        template="plotly_dark",
        title=f"<b>JP 레이더: {result.sector.name} · 일봉/주봉 멀티 타임프레임</b>",
        height=1000,
        legend_tracegroupgap=150,
        yaxis=dict(title="스토캐스틱 에너지 (0-10)", range=[0, 10.5]),
        yaxis3=dict(title="스토캐스틱 에너지 (0-10)", range=[0, 10.5]),
        yaxis2=dict(title=result.sector.benchmark_name, showgrid=False),
        yaxis4=dict(title=result.sector.benchmark_name, showgrid=False),
    )
    fig.update_xaxes(rangeslider=dict(visible=True), row=2, col=1)
    fig.update_xaxes(rangeslider=dict(visible=True), row=2, col=2)
    return fig


def _add_timeframe(fig: go.Figure, frame: TimeframeRadarResult, suffix: str, row: int, col: int, macd_row: int, macd_col: int) -> None:
    for prefix, attr, color in ENERGY_LINES:
        data = getattr(frame, attr)
        fig.add_trace(
            go.Scatter(x=data.index, y=data, name=f"{prefix}{suffix}", line=dict(color=color, width=1.5, dash="dot"), legendgroup=suffix),
            row=row,
            col=col,
            secondary_y=False,
        )
    bench = frame.benchmark.dropna()
    bench_val = f"{bench.iloc[-1]:,.2f}" if len(bench) else "-"
    fig.add_trace(
        go.Scatter(x=bench.index, y=bench, name=f"{suffix} 지수: {bench_val}", line=dict(color="white", width=2), legendgroup=suffix),
        row=row,
        col=col,
        secondary_y=True,
    )
    fig.add_trace(go.Scatter(x=frame.macd.index, y=frame.macd, name=f"MACD ({suffix})", line=dict(color="cyan", width=1.5), legendgroup=suffix), row=macd_row, col=macd_col)
    fig.add_trace(go.Scatter(x=frame.signal.index, y=frame.signal, name=f"Signal ({suffix})", line=dict(color="magenta", width=1.5), legendgroup=suffix), row=macd_row, col=macd_col)

    buy_dates = frame.index.index[frame.buy_signal]
    sell_dates = frame.index.index[frame.sell_signal]
    fig.add_trace(go.Scatter(x=buy_dates, y=frame.macd.loc[buy_dates], mode="markers", name=f"{suffix} 매수", marker=dict(color="lime", size=10, symbol="circle"), legendgroup=suffix), row=macd_row, col=macd_col)
    fig.add_trace(go.Scatter(x=sell_dates, y=frame.macd.loc[sell_dates], mode="markers", name=f"{suffix} 매도", marker=dict(color="yellow", size=10, symbol="x"), legendgroup=suffix), row=macd_row, col=macd_col)

    buy_bench = buy_dates.intersection(bench.index)
    sell_bench = sell_dates.intersection(bench.index)
    fig.add_trace(go.Scatter(x=buy_bench, y=bench.loc[buy_bench], mode="markers", marker=dict(color="lime", size=10, symbol="circle"), showlegend=False, legendgroup=suffix), row=row, col=col, secondary_y=True)
    fig.add_trace(go.Scatter(x=sell_bench, y=bench.loc[sell_bench], mode="markers", marker=dict(color="yellow", size=10, symbol="x"), showlegend=False, legendgroup=suffix), row=row, col=col, secondary_y=True)
