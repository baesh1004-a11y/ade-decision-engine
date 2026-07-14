from __future__ import annotations

from datetime import timedelta

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from jp_radar.live_engine import IntradayRadarResult


COLORS = ["#ff5b5b", "#ff9f43", "#f5d547", "#4cd97b", "#3aa6ff", "#a970ff"]


def make_live_radar_chart(
    result: IntradayRadarResult,
    mobile: bool = False,
    period_days: int = 365,
) -> go.Figure:
    fig = make_subplots(
        rows=6,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.025 if not mobile else 0.035,
        row_heights=[0.20, 0.11, 0.20, 0.11, 0.20, 0.11],
        specs=[
            [{"secondary_y": True}], [{"secondary_y": False}],
            [{"secondary_y": True}], [{"secondary_y": False}],
            [{"secondary_y": True}], [{"secondary_y": False}],
        ],
        subplot_titles=(
            "1. 120분봉 에너지 · 가격", "2. 120분봉 MACD",
            "3. 일봉 에너지 · 가격", "4. 일봉 MACD",
            "5. 주봉 에너지 · 가격", "6. 주봉 MACD",
        ),
    )

    radar = result.radar
    frames = [
        (result.radar_120m, result.intraday_price, "120m", 1, 2),
        (radar.daily, radar.daily.benchmark.dropna(), "D", 3, 4),
        (radar.weekly, radar.weekly.benchmark.dropna(), "W", 5, 6),
    ]
    for timeframe, price, label, energy_row, macd_row in frames:
        _add_timeframe(fig, timeframe, price, label, energy_row, macd_row, mobile)
        _add_meaning_lines(fig, result, price, energy_row)

    _add_yearly_lines(fig, result)

    latest = max(
        [series.index.max() for _, series, _, _, _ in frames if not series.empty],
        default=None,
    )
    cutoff = latest - timedelta(days=period_days) if latest is not None else None

    fig.update_layout(
        template="plotly_dark",
        height=1250 if mobile else 1700,
        margin=dict(l=12 if mobile else 48, r=12 if mobile else 190, t=75, b=80),
        paper_bgcolor="#0b1118",
        plot_bgcolor="#0b1118",
        hovermode="x unified",
        dragmode="pan" if mobile else "zoom",
        legend=dict(
            orientation="h" if mobile else "v",
            x=0 if mobile else 1.01,
            y=-0.03 if mobile else 1.0,
            xanchor="left",
            yanchor="top",
            font=dict(size=8 if mobile else 10),
            bgcolor="rgba(14,22,31,.94)",
            bordercolor="#2a3949",
            borderwidth=1,
            groupclick="toggleitem",
        ),
        font=dict(size=9 if mobile else 11, color="#dce6f0"),
        autosize=True,
    )

    for row in [1, 3, 5]:
        fig.update_yaxes(range=[0, 10.5], title_text="에너지", row=row, col=1, secondary_y=False, gridcolor="#25303c")
        fig.update_yaxes(title_text="가격", row=row, col=1, secondary_y=True, gridcolor="rgba(0,0,0,0)")
        fig.add_hline(y=2, line_dash="dash", line_color="#25d366", opacity=0.5, row=row, col=1)
        fig.add_hline(y=8, line_dash="dash", line_color="#ff5b5b", opacity=0.5, row=row, col=1)
    for row in [2, 4, 6]:
        fig.update_yaxes(title_text="MACD", row=row, col=1, gridcolor="#25303c")
        fig.add_hline(y=0, line_dash="dot", line_color="#657383", opacity=0.7, row=row, col=1)

    for row in range(1, 7):
        fig.update_xaxes(gridcolor="#202a35", row=row, col=1, rangeslider=dict(visible=False))
    if cutoff is not None:
        fig.update_xaxes(range=[cutoff, latest], row=3, col=1)
        fig.update_xaxes(range=[cutoff, latest], row=4, col=1)
        fig.update_xaxes(range=[cutoff, latest], row=5, col=1)
        fig.update_xaxes(range=[cutoff, latest], row=6, col=1)
    fig.update_xaxes(
        row=6,
        col=1,
        rangeslider=dict(visible=not mobile),
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1개월", step="month", stepmode="backward"),
                dict(count=3, label="3개월", step="month", stepmode="backward"),
                dict(count=1, label="1년", step="year", stepmode="backward"),
                dict(step="all", label="전체"),
            ]
        ) if not mobile else None,
    )
    return fig


def _add_timeframe(fig, timeframe, price, label: str, energy_row: int, macd_row: int, mobile: bool) -> None:
    lines = [
        ("단기 K", timeframe.s_k), ("단기 D", timeframe.s_d),
        ("중기 K", timeframe.m_k), ("중기 D", timeframe.m_d),
        ("장기 K", timeframe.l_k), ("장기 D", timeframe.l_d),
    ]
    for idx, (name, series) in enumerate(lines):
        fig.add_trace(
            go.Scatter(
                x=series.index, y=series, name=f"{label} {name}", legendgroup=label,
                line=dict(color=COLORS[idx], width=1.4, dash="dot" if idx % 2 else "solid"),
                visible=True if idx in {0, 2, 4} else "legendonly",
                hovertemplate=f"{label} {name} %{{y:.2f}}<extra></extra>",
            ),
            row=energy_row, col=1, secondary_y=False,
        )

    if not price.empty:
        fig.add_trace(
            go.Scatter(
                x=price.index, y=price, name=f"{label} 원본가격", legendgroup=f"{label}-price",
                line=dict(color="#f4f7fb", width=2.2),
                hovertemplate=f"{label} 가격 %{{y:,.2f}}<extra></extra>",
            ),
            row=energy_row, col=1, secondary_y=True,
        )

    fig.add_trace(
        go.Scatter(x=timeframe.macd.index, y=timeframe.macd, name=f"{label} MACD", legendgroup=f"{label}-macd", line=dict(color="#22d3ee", width=1.7)),
        row=macd_row, col=1,
    )
    fig.add_trace(
        go.Scatter(x=timeframe.signal.index, y=timeframe.signal, name=f"{label} Signal", legendgroup=f"{label}-macd", line=dict(color="#ec4cff", width=1.7)),
        row=macd_row, col=1,
    )

    buy_dates = timeframe.buy_signal[timeframe.buy_signal].index.intersection(price.index)
    sell_dates = timeframe.sell_signal[timeframe.sell_signal].index.intersection(price.index)
    if len(buy_dates):
        fig.add_trace(go.Scatter(x=buy_dates, y=price.loc[buy_dates], mode="markers", name=f"{label} 매수", legendgroup=f"{label}-signal", marker=dict(color="#2cff68", size=7, symbol="circle"), visible="legendonly" if mobile else True), row=energy_row, col=1, secondary_y=True)
    if len(sell_dates):
        fig.add_trace(go.Scatter(x=sell_dates, y=price.loc[sell_dates], mode="markers", name=f"{label} 매도", legendgroup=f"{label}-signal", marker=dict(color="#ffe34f", size=8, symbol="x"), visible="legendonly" if mobile else True), row=energy_row, col=1, secondary_y=True)


def _add_meaning_lines(fig: go.Figure, result: IntradayRadarResult, price, row: int) -> None:
    if price.empty or not result.meaningful_lines:
        return
    start, end = price.index.min(), price.index.max()
    palette = {"W": "#66c2ff", "M": "#b388ff", "Y": "#ffb74d"}
    for item in result.meaningful_lines:
        fig.add_trace(
            go.Scatter(
                x=[start, end], y=[item.price, item.price], mode="lines",
                name=f"{item.timeframe} 의미선 {item.line_type} {item.price:,.0f}",
                legendgroup=f"meaning-{item.timeframe}",
                line=dict(color=palette.get(item.timeframe, "#9aa7b3"), width=1, dash="dot"),
                opacity=0.32,
                visible="legendonly" if row != 3 else True,
                hovertemplate=f"{item.timeframe} 거래대금 의미선 {item.price:,.2f}<extra></extra>",
            ),
            row=row, col=1, secondary_y=True,
        )


def _add_yearly_lines(fig: go.Figure, result: IntradayRadarResult) -> None:
    yearly = result.radar.yearly
    for row, price in [(1, result.intraday_price), (3, result.radar.daily.benchmark.dropna()), (5, result.radar.weekly.benchmark.dropna())]:
        if price.empty:
            continue
        start, end = price.index.min(), price.index.max()
        fig.add_trace(go.Scatter(x=[start, end], y=[yearly.open, yearly.open], mode="lines", name=f"{yearly.year} 연봉 시가", legendgroup="yearly", line=dict(color="#ff9f43", width=1.8, dash="dash"), visible=True if row == 3 else "legendonly"), row=row, col=1, secondary_y=True)
        if yearly.show_close_line:
            fig.add_trace(go.Scatter(x=[start, end], y=[yearly.close, yearly.close], mode="lines", name=f"{yearly.year} 연봉 종가", legendgroup="yearly", line=dict(color="#ff6680", width=1.8, dash="dot"), visible=True if row == 3 else "legendonly"), row=row, col=1, secondary_y=True)
