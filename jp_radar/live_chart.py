from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from jp_radar.live_engine import IntradayRadarResult


ENERGY_LINES = [
    ("빨D", "s_k", "red"),
    ("주D", "s_d", "orange"),
    ("노D", "m_k", "yellow"),
    ("초D", "m_d", "green"),
    ("파D", "l_k", "blue"),
    ("남D", "l_d", "purple"),
]


def make_live_radar_chart(result: IntradayRadarResult, mobile: bool = False) -> go.Figure:
    radar = result.radar
    daily = radar.daily
    intraday = result.intraday_price

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.10 if mobile else 0.06,
        row_heights=[0.68, 0.32] if mobile else [0.58, 0.42],
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
        subplot_titles=(
            "에너지 · 지수 · 연봉 의미선" if mobile else f"JP 레이더 · {radar.sector.name} · 일봉/주봉 에너지 + 실시간 지수 + 연봉 의미선",
            "MACD" if mobile else "실시간 MACD",
        ),
    )

    for idx, (name, attr, color) in enumerate(ENERGY_LINES):
        data = getattr(daily, attr)
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data,
                name=name,
                line=dict(color=color, width=1.6, dash="dot"),
                visible=True if not mobile or idx < 2 else "legendonly",
            ),
            row=1,
            col=1,
            secondary_y=False,
        )

    weekly = radar.weekly
    weekly_lines = [
        ("주봉 단기", weekly.s_k, "#ffd54f"),
        ("주봉 중기", weekly.m_k, "#66bb6a"),
        ("주봉 장기", weekly.l_k, "#42a5f5"),
    ]
    for idx, (name, data, color) in enumerate(weekly_lines):
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data,
                name=name,
                line=dict(color=color, width=2.0),
                opacity=0.78,
                visible=True if not mobile or idx == 0 else "legendonly",
            ),
            row=1,
            col=1,
            secondary_y=False,
        )

    bench = daily.benchmark.dropna()
    fig.add_trace(
        go.Scatter(
            x=bench.index,
            y=bench,
            name=f"{radar.sector.benchmark_name} 일봉",
            line=dict(color="white", width=2.1),
        ),
        row=1,
        col=1,
        secondary_y=True,
    )

    if not intraday.empty:
        fig.add_trace(
            go.Scatter(
                x=intraday.index,
                y=intraday,
                name=f"실시간 {result.latest_price:,.2f}",
                line=dict(color="#00e5ff", width=2.5),
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

    _add_yearly_meaning_lines(fig, result)

    buy_dates = daily.index.index[daily.buy_signal]
    sell_dates = daily.index.index[daily.sell_signal]
    buy_dates = buy_dates.intersection(bench.index)
    sell_dates = sell_dates.intersection(bench.index)

    if len(buy_dates):
        fig.add_trace(
            go.Scatter(
                x=buy_dates,
                y=bench.loc[buy_dates],
                mode="markers",
                name="매수 신호",
                marker=dict(color="lime", size=10, symbol="circle"),
                visible="legendonly" if mobile else True,
            ),
            row=1,
            col=1,
            secondary_y=True,
        )
    if len(sell_dates):
        fig.add_trace(
            go.Scatter(
                x=sell_dates,
                y=bench.loc[sell_dates],
                mode="markers",
                name="매도 신호",
                marker=dict(color="yellow", size=10, symbol="x"),
                visible="legendonly" if mobile else True,
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

    fig.add_trace(
        go.Scatter(
            x=result.intraday_macd.index,
            y=result.intraday_macd,
            name="MACD",
            line=dict(color="cyan", width=1.8),
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=result.intraday_signal.index,
            y=result.intraday_signal,
            name="Signal",
            line=dict(color="magenta", width=1.8),
        ),
        row=2,
        col=1,
    )

    fig.add_hline(y=2, line_dash="dash", line_color="lime", opacity=0.5, row=1, col=1)
    fig.add_hline(y=8, line_dash="dash", line_color="red", opacity=0.5, row=1, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="#708090", opacity=0.6, row=2, col=1)

    if mobile:
        legend = dict(
            orientation="h",
            x=0,
            y=-0.19,
            xanchor="left",
            yanchor="top",
            font=dict(size=10),
            bgcolor="rgba(17,25,35,.82)",
            bordercolor="#27384a",
            borderwidth=1,
            itemwidth=48,
        )
        margin = dict(l=8, r=8, t=72, b=150)
        title = f"<b>JP Radar · {radar.sector.name}</b><br><sup>{result.updated_at}</sup>"
        height = 760
    else:
        legend = dict(orientation="v", x=1.01, y=1.0)
        margin = dict(l=40, r=40, t=80, b=40)
        title = (
            f"<b>JP Radar Live · {radar.sector.name}</b>"
            f"<br><sup>{result.source} · {result.updated_at}</sup>"
        )
        height = 980

    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=margin,
        paper_bgcolor="#0b0f14",
        plot_bgcolor="#0b0f14",
        legend=legend,
        hovermode="x unified",
        title=title,
        font=dict(size=11 if mobile else 13),
        autosize=True,
        dragmode="pan" if mobile else "zoom",
    )
    fig.update_yaxes(
        title_text="에너지" if mobile else "에너지 0~10",
        range=[0, 10.5],
        row=1,
        col=1,
        secondary_y=False,
        title_font=dict(size=10 if mobile else 13),
        tickfont=dict(size=9 if mobile else 12),
        automargin=True,
    )
    fig.update_yaxes(
        title_text="지수" if mobile else radar.sector.benchmark_name,
        row=1,
        col=1,
        secondary_y=True,
        title_font=dict(size=10 if mobile else 13),
        tickfont=dict(size=9 if mobile else 12),
        automargin=True,
    )
    fig.update_yaxes(
        title_text="MACD",
        row=2,
        col=1,
        title_font=dict(size=10 if mobile else 13),
        tickfont=dict(size=9 if mobile else 12),
        automargin=True,
    )
    fig.update_xaxes(
        tickfont=dict(size=9 if mobile else 12),
        automargin=True,
        rangeslider=dict(visible=False if mobile else True),
        row=2,
        col=1,
    )
    fig.update_xaxes(tickfont=dict(size=9 if mobile else 12), automargin=True, row=1, col=1)
    return fig


def _add_yearly_meaning_lines(fig: go.Figure, result: IntradayRadarResult) -> None:
    yearly = result.radar.yearly
    bench = result.radar.daily.benchmark.dropna()
    intraday = result.intraday_price.dropna()
    if bench.empty and intraday.empty:
        return

    start = bench.index.min() if not bench.empty else intraday.index.min()
    end_candidates = []
    if not bench.empty:
        end_candidates.append(bench.index.max())
    if not intraday.empty:
        end_candidates.append(intraday.index.max())
    end = max(end_candidates)

    fig.add_trace(
        go.Scatter(
            x=[start, end],
            y=[yearly.open, yearly.open],
            mode="lines",
            name=f"{yearly.year} 연봉 시가 {yearly.open:,.2f}",
            line=dict(color="#ff9f43", width=2.2, dash="dash"),
            hovertemplate="연봉 시가 %{y:,.2f}<extra></extra>",
        ),
        row=1,
        col=1,
        secondary_y=True,
    )

    if yearly.show_close_line:
        fig.add_trace(
            go.Scatter(
                x=[start, end],
                y=[yearly.close, yearly.close],
                mode="lines",
                name=f"{yearly.year} 연봉 종가 {yearly.close:,.2f}",
                line=dict(color="#ff4d6d", width=2.2, dash="dot"),
                hovertemplate="연봉 종가 %{y:,.2f}<extra></extra>",
            ),
            row=1,
            col=1,
            secondary_y=True,
        )
