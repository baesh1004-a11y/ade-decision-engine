from __future__ import annotations

from datetime import timedelta

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from jp_radar.live_engine import IntradayRadarResult


ENERGY_LINES = [
    ("일봉 단기", "s_k", "#ff5b5b"),
    ("일봉 보조", "s_d", "#ff9f43"),
    ("일봉 중기", "m_k", "#f5d547"),
    ("일봉 중기 보조", "m_d", "#4cd97b"),
    ("일봉 장기", "l_k", "#3aa6ff"),
    ("일봉 장기 보조", "l_d", "#a970ff"),
]


def make_live_radar_chart(
    result: IntradayRadarResult,
    mobile: bool = False,
    period_days: int = 365,
) -> go.Figure:
    radar = result.radar
    daily = radar.daily
    intraday = result.intraday_price
    bench = daily.benchmark.dropna()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.12 if mobile else 0.09,
        row_heights=[0.69, 0.31],
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
        subplot_titles=("가격 · 에너지 · 연봉 의미선", "실시간 MACD"),
    )

    for idx, (name, attr, color) in enumerate(ENERGY_LINES):
        data = getattr(daily, attr)
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data,
                name=name,
                legendgroup="daily",
                line=dict(color=color, width=1.5, dash="dot"),
                opacity=0.82,
                visible=True if idx in {0, 2} else "legendonly",
                hovertemplate=f"{name} %{{y:.2f}}<extra></extra>",
            ),
            row=1,
            col=1,
            secondary_y=False,
        )

    weekly = radar.weekly
    weekly_lines = [
        ("주봉 단기", weekly.s_k, "#ffe45c", True),
        ("주봉 중기", weekly.m_k, "#62d98b", True),
        ("주봉 장기", weekly.l_k, "#52a9ff", False),
    ]
    for name, data, color, default_visible in weekly_lines:
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data,
                name=name,
                legendgroup="weekly",
                line=dict(color=color, width=2.1),
                opacity=0.92,
                visible=True if default_visible else "legendonly",
                hovertemplate=f"{name} %{{y:.2f}}<extra></extra>",
            ),
            row=1,
            col=1,
            secondary_y=False,
        )

    fig.add_trace(
        go.Scatter(
            x=bench.index,
            y=bench,
            name=f"{radar.sector.benchmark_name} 일봉",
            legendgroup="price",
            line=dict(color="#f4f7fb", width=2.4),
            hovertemplate="지수 %{y:,.2f}<extra></extra>",
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
                legendgroup="price",
                line=dict(color="#16d9ff", width=2.8),
                hovertemplate="실시간 %{y:,.2f}<extra></extra>",
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

    _add_yearly_meaning_lines(fig, result)

    latest_main_date = None
    if not bench.empty:
        latest_main_date = bench.index.max()
    if not intraday.empty:
        latest_main_date = max(latest_main_date, intraday.index.max()) if latest_main_date is not None else intraday.index.max()
    cutoff = latest_main_date - timedelta(days=period_days) if latest_main_date is not None else None

    buy_dates = daily.index.index[daily.buy_signal].intersection(bench.index)
    sell_dates = daily.index.index[daily.sell_signal].intersection(bench.index)
    if cutoff is not None:
        buy_dates = buy_dates[buy_dates >= cutoff]
        sell_dates = sell_dates[sell_dates >= cutoff]

    if len(buy_dates):
        fig.add_trace(
            go.Scatter(
                x=buy_dates,
                y=bench.loc[buy_dates],
                mode="markers",
                name="매수 신호",
                legendgroup="signal",
                marker=dict(color="#2cff68", size=8, symbol="circle", line=dict(color="#0b0f14", width=1)),
                visible="legendonly" if mobile else True,
                hovertemplate="매수 %{x|%Y-%m-%d}<extra></extra>",
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
                legendgroup="signal",
                marker=dict(color="#ffe34f", size=9, symbol="x"),
                visible="legendonly" if mobile else True,
                hovertemplate="매도 %{x|%Y-%m-%d}<extra></extra>",
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
            legendgroup="macd",
            line=dict(color="#22d3ee", width=2.0),
            hovertemplate="MACD %{y:.2f}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=result.intraday_signal.index,
            y=result.intraday_signal,
            name="Signal",
            legendgroup="macd",
            line=dict(color="#ec4cff", width=2.0),
            hovertemplate="Signal %{y:.2f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    fig.add_hline(y=2, line_dash="dash", line_color="#25d366", opacity=0.55, row=1, col=1)
    fig.add_hline(y=8, line_dash="dash", line_color="#ff5b5b", opacity=0.55, row=1, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="#657383", opacity=0.7, row=2, col=1)

    if mobile:
        legend = dict(
            orientation="h",
            x=0,
            y=-0.22,
            xanchor="left",
            yanchor="top",
            font=dict(size=9),
            bgcolor="rgba(14,22,31,.92)",
            bordercolor="#2a3949",
            borderwidth=1,
            itemwidth=46,
        )
        margin = dict(l=8, r=8, t=60, b=155)
        height = 760
    else:
        legend = dict(
            orientation="v",
            x=1.015,
            y=1.0,
            xanchor="left",
            yanchor="top",
            font=dict(size=11),
            bgcolor="rgba(14,22,31,.94)",
            bordercolor="#2a3949",
            borderwidth=1,
            itemsizing="constant",
            tracegroupgap=5,
        )
        margin = dict(l=48, r=185, t=62, b=42)
        height = 760

    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=margin,
        paper_bgcolor="#0b1118",
        plot_bgcolor="#0b1118",
        legend=legend,
        hovermode="x unified",
        title=None,
        font=dict(size=10 if mobile else 12, color="#dce6f0"),
        autosize=True,
        dragmode="pan" if mobile else "zoom",
        hoverlabel=dict(bgcolor="#111a24", font_size=11),
    )

    fig.update_annotations(font=dict(size=12 if mobile else 14, color="#dce6f0"))
    fig.update_yaxes(
        title_text="에너지",
        range=[0, 10.5],
        row=1,
        col=1,
        secondary_y=False,
        gridcolor="#25303c",
        zeroline=False,
        tickfont=dict(size=9 if mobile else 11),
        title_font=dict(size=10 if mobile else 12),
        automargin=True,
    )
    fig.update_yaxes(
        title_text="지수",
        row=1,
        col=1,
        secondary_y=True,
        gridcolor="rgba(0,0,0,0)",
        tickfont=dict(size=9 if mobile else 11),
        title_font=dict(size=10 if mobile else 12),
        automargin=True,
    )
    fig.update_yaxes(
        title_text="MACD",
        row=2,
        col=1,
        gridcolor="#25303c",
        tickfont=dict(size=9 if mobile else 11),
        title_font=dict(size=10 if mobile else 12),
        automargin=True,
    )
    fig.update_xaxes(
        row=1,
        col=1,
        gridcolor="#202a35",
        tickfont=dict(size=9 if mobile else 11),
        automargin=True,
        range=[cutoff, latest_main_date] if cutoff is not None else None,
    )
    fig.update_xaxes(
        row=2,
        col=1,
        gridcolor="#202a35",
        tickfont=dict(size=9 if mobile else 11),
        automargin=True,
        rangeslider=dict(visible=False),
    )
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
            name=f"{yearly.year} 연봉 시가",
            legendgroup="yearly",
            line=dict(color="#ff9f43", width=2.0, dash="dash"),
            hovertemplate=f"연봉 시가 {yearly.open:,.2f}<extra></extra>",
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
                name=f"{yearly.year} 연봉 종가",
                legendgroup="yearly",
                line=dict(color="#ff6680", width=2.0, dash="dot"),
                hovertemplate=f"연봉 종가 {yearly.close:,.2f}<extra></extra>",
            ),
            row=1,
            col=1,
            secondary_y=True,
        )
