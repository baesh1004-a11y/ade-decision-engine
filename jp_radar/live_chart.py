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
    """Compact JP Radar chart: 120m energy/price plus one 120m MACD panel."""
    radar = result.radar_120m
    price = result.intraday_price.dropna()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.68, 0.32],
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
        subplot_titles=("120분봉 에너지 · 가격 · 주/월/연 의미선", "120분봉 MACD"),
    )

    energy_lines = [
        ("빨 D", radar.s_k),
        ("주 D", radar.s_d),
        ("노 D", radar.m_k),
        ("초 D", radar.m_d),
        ("파 D", radar.l_k),
        ("남 D", radar.l_d),
    ]
    for idx, (name, series) in enumerate(energy_lines):
        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series,
                name=f"{name} : {series.iloc[-1]:.2f}" if not series.empty else name,
                legendgroup="energy",
                line=dict(color=COLORS[idx], width=1.35, dash="dot"),
                hovertemplate=f"{name} %{{y:.2f}}<extra></extra>",
            ),
            row=1,
            col=1,
            secondary_y=False,
        )

    if not price.empty:
        fig.add_trace(
            go.Scatter(
                x=price.index,
                y=price,
                name=f"현재가 : {result.latest_price:,.2f}",
                legendgroup="price",
                line=dict(color="#f7f7f7", width=2.3),
                hovertemplate="가격 %{y:,.2f}<extra></extra>",
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

    _add_meaning_lines(fig, result, price)
    _add_signals(fig, radar, price, mobile)

    fig.add_trace(
        go.Scatter(
            x=radar.macd.index,
            y=radar.macd,
            name=f"MACD : {radar.macd.iloc[-1]:.2f}" if not radar.macd.empty else "MACD",
            legendgroup="macd",
            line=dict(color="#22d3ee", width=1.8),
            hovertemplate="MACD %{y:.2f}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=radar.signal.index,
            y=radar.signal,
            name=f"Signal : {radar.signal.iloc[-1]:.2f}" if not radar.signal.empty else "Signal",
            legendgroup="macd",
            line=dict(color="#ec4cff", width=1.8),
            hovertemplate="Signal %{y:.2f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    _add_macd_signal_markers(fig, radar)

    latest = price.index.max() if not price.empty else None
    visible_days = min(max(int(period_days), 14), 90)
    cutoff = latest - timedelta(days=visible_days) if latest is not None else None

    fig.add_hline(y=2, line_dash="dash", line_color="#25d366", opacity=0.7, row=1, col=1)
    fig.add_hline(y=8, line_dash="dash", line_color="#ff5b5b", opacity=0.7, row=1, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="#d8dde3", opacity=0.55, row=2, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=690 if mobile else 760,
        margin=dict(l=10 if mobile else 42, r=10 if mobile else 175, t=62, b=45),
        paper_bgcolor="#0b1118",
        plot_bgcolor="#0b1118",
        hovermode="x unified",
        dragmode="pan" if mobile else "zoom",
        legend=dict(
            orientation="h" if mobile else "v",
            x=0 if mobile else 1.01,
            y=-0.13 if mobile else 1.0,
            xanchor="left",
            yanchor="top",
            font=dict(size=8 if mobile else 10),
            bgcolor="rgba(14,22,31,.94)",
            bordercolor="#2a3949",
            borderwidth=1,
            tracegroupgap=3,
        ),
        font=dict(size=9 if mobile else 11, color="#dce6f0"),
        autosize=True,
    )

    fig.update_yaxes(
        title_text="스토캐스틱 에너지 (0~10)",
        range=[0, 10.5],
        row=1,
        col=1,
        secondary_y=False,
        gridcolor="#27323d",
        zeroline=False,
    )
    fig.update_yaxes(
        title_text="가격",
        row=1,
        col=1,
        secondary_y=True,
        gridcolor="rgba(0,0,0,0)",
    )
    fig.update_yaxes(title_text="MACD", row=2, col=1, gridcolor="#27323d")

    for row in [1, 2]:
        fig.update_xaxes(gridcolor="#202a35", row=row, col=1, rangeslider=dict(visible=False))
    if cutoff is not None:
        fig.update_xaxes(range=[cutoff, latest], row=1, col=1)
        fig.update_xaxes(range=[cutoff, latest], row=2, col=1)

    fig.update_xaxes(
        row=2,
        col=1,
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1개월", step="month", stepmode="backward"),
                dict(count=2, label="2개월", step="month", stepmode="backward"),
                dict(count=3, label="3개월", step="month", stepmode="backward"),
                dict(step="all", label="전체"),
            ]
        ) if not mobile else None,
    )
    return fig


def _add_meaning_lines(fig: go.Figure, result: IntradayRadarResult, price) -> None:
    if price.empty:
        return
    start, end = price.index.min(), price.index.max()
    palette = {"W": "#5ec8ff", "M": "#f4d35e", "Y": "#ff9f43"}
    dash = {"W": "dot", "M": "dash", "Y": "longdash"}

    for item in result.meaningful_lines:
        fig.add_trace(
            go.Scatter(
                x=[start, end],
                y=[item.price, item.price],
                mode="lines",
                name=f"{item.timeframe} {item.line_type} ₩{item.price:,.0f}",
                legendgroup=f"meaning-{item.timeframe}",
                line=dict(
                    color=palette.get(item.timeframe, "#9aa7b3"),
                    width=1.15,
                    dash=dash.get(item.timeframe, "dot"),
                ),
                opacity=0.72,
                hovertemplate=f"{item.timeframe} 거래대금 의미선 {item.price:,.2f}<extra></extra>",
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

    yearly = result.radar.yearly
    fig.add_trace(
        go.Scatter(
            x=[start, end],
            y=[yearly.open, yearly.open],
            mode="lines",
            name=f"연봉 시가 ₩{yearly.open:,.0f}",
            legendgroup="yearly",
            line=dict(color="#ffb347", width=1.8, dash="dash"),
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
                name=f"연봉 종가 ₩{yearly.close:,.0f}",
                legendgroup="yearly",
                line=dict(color="#ff6680", width=1.8, dash="dot"),
                hovertemplate=f"연봉 종가 {yearly.close:,.2f}<extra></extra>",
            ),
            row=1,
            col=1,
            secondary_y=True,
        )


def _add_signals(fig: go.Figure, radar, price, mobile: bool) -> None:
    if price.empty:
        return
    buy_dates = radar.buy_signal[radar.buy_signal].index.intersection(price.index)
    sell_dates = radar.sell_signal[radar.sell_signal].index.intersection(price.index)
    if len(buy_dates):
        fig.add_trace(
            go.Scatter(
                x=buy_dates,
                y=price.loc[buy_dates],
                mode="markers",
                name="매수",
                legendgroup="signal",
                marker=dict(color="#2cff68", size=8, symbol="circle"),
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
                y=price.loc[sell_dates],
                mode="markers",
                name="매도",
                legendgroup="signal",
                marker=dict(color="#ffe34f", size=8, symbol="x"),
                visible="legendonly" if mobile else True,
            ),
            row=1,
            col=1,
            secondary_y=True,
        )


def _add_macd_signal_markers(fig: go.Figure, radar) -> None:
    buy_dates = radar.buy_signal[radar.buy_signal].index.intersection(radar.macd.index)
    sell_dates = radar.sell_signal[radar.sell_signal].index.intersection(radar.macd.index)
    if len(buy_dates):
        fig.add_trace(
            go.Scatter(
                x=buy_dates,
                y=radar.macd.loc[buy_dates],
                mode="markers",
                name="MACD 매수",
                legendgroup="signal",
                marker=dict(color="#2cff68", size=7, symbol="circle"),
                showlegend=False,
            ),
            row=2,
            col=1,
        )
    if len(sell_dates):
        fig.add_trace(
            go.Scatter(
                x=sell_dates,
                y=radar.macd.loc[sell_dates],
                mode="markers",
                name="MACD 매도",
                legendgroup="signal",
                marker=dict(color="#ffe34f", size=8, symbol="x"),
                showlegend=False,
            ),
            row=2,
            col=1,
        )
