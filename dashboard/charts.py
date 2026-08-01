from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


CHART_CONFIG = {
    "displayModeBar": True,
    "scrollZoom": True,
    "responsive": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
}

FONT_FAMILY = "Pretendard, Inter, Apple SD Gothic Neo, Noto Sans KR, Arial, sans-serif"
BG = "#0A0F15"
PANEL = "#101821"
GRID = "rgba(116,134,151,.16)"
TEXT = "#E8EEF4"
MUTED = "#8E9DAC"
UP = "#FF5B67"
DOWN = "#4F8FFF"
MA20 = "#F4B860"
BB = "#39D98A"
STO_K = "#7CB6FF"
STO_D = "#F6A65B"


def stochastic_ohlc(df: pd.DataFrame, period: int = 14, smooth: int = 3):
    lowest = df["Low"].rolling(period, min_periods=1).min()
    highest = df["High"].rolling(period, min_periods=1).max()
    k = ((df["Close"] - lowest) / (highest - lowest).replace(0, 1) * 100).fillna(50)
    d = k.rolling(smooth, min_periods=1).mean()
    return k, d


def _axis_style() -> dict:
    return {
        "showgrid": True,
        "gridcolor": GRID,
        "zeroline": False,
        "showline": False,
        "ticks": "outside",
        "tickfont": {"family": FONT_FAMILY, "size": 10, "color": MUTED},
        "fixedrange": False,
    }


def build_trading_chart(data: pd.DataFrame, title: str, *, height: int = 620) -> go.Figure:
    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna().reset_index(drop=True)

    df["SMA20"] = df["Close"].rolling(20, min_periods=1).mean()
    std20 = df["Close"].rolling(20, min_periods=1).std().fillna(0)
    df["BB_UPPER"] = df["SMA20"] + std20 * 2
    df["BB_LOWER"] = df["SMA20"] - std20 * 2
    k, d = stochastic_ohlc(df)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.015,
        row_heights=[0.68, 0.14, 0.18],
    )

    fig.add_trace(
        go.Candlestick(
            x=df["Date"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=title,
            increasing_line_color=UP,
            increasing_fillcolor=UP,
            decreasing_line_color=DOWN,
            decreasing_fillcolor=DOWN,
            whiskerwidth=0.45,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"],
            y=df["BB_UPPER"],
            name="BB 상단",
            line=dict(color=BB, width=1.2),
            hovertemplate="BB 상단 %{y:,.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"],
            y=df["SMA20"],
            name="SMA20",
            line=dict(color=MA20, width=1.8),
            hovertemplate="SMA20 %{y:,.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"],
            y=df["BB_LOWER"],
            name="BB 하단",
            line=dict(color=BB, width=1.2),
            fill="tonexty",
            fillcolor="rgba(57,217,138,.05)",
            hovertemplate="BB 하단 %{y:,.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    volume_colors = [
        "rgba(255,91,103,.52)" if close >= open_ else "rgba(79,143,255,.52)"
        for close, open_ in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(
        go.Bar(
            x=df["Date"],
            y=df["Volume"],
            name="거래량",
            marker_color=volume_colors,
            hovertemplate="거래량 %{y:,.0f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(x=df["Date"], y=k, name="STO %K", line=dict(color=STO_K, width=1.6)),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["Date"], y=d, name="STO %D", line=dict(color=STO_D, width=1.6)),
        row=3,
        col=1,
    )
    fig.add_hline(y=80, line_dash="dot", line_color="rgba(255,91,103,.55)", row=3, col=1)
    fig.add_hline(y=20, line_dash="dot", line_color="rgba(79,143,255,.55)", row=3, col=1)

    latest = df.iloc[-1]
    latest_change = (float(latest["Close"]) / float(df.iloc[-2]["Close"]) - 1) * 100 if len(df) > 1 else 0.0
    latest_color = UP if latest_change >= 0 else DOWN
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0,
        y=1.07,
        showarrow=False,
        align="left",
        text=(
            f"<b>{title}</b> &nbsp; "
            f"<span style='color:{latest_color}'>{float(latest['Close']):,.2f} ({latest_change:+.2f}%)</span> &nbsp; "
            f"O {float(latest['Open']):,.2f} &nbsp; H {float(latest['High']):,.2f} &nbsp; "
            f"L {float(latest['Low']):,.2f} &nbsp; V {float(latest['Volume']):,.0f}"
        ),
        font=dict(family=FONT_FAMILY, size=12, color=TEXT),
    )

    fig.update_layout(
        height=height,
        margin=dict(l=10, r=58, t=56, b=10),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        dragmode="pan",
        legend=dict(
            orientation="h",
            y=1.015,
            x=1,
            xanchor="right",
            bgcolor="rgba(16,24,33,.78)",
            bordercolor="rgba(116,134,151,.22)",
            borderwidth=1,
            font=dict(size=10, family=FONT_FAMILY, color=TEXT),
        ),
        font=dict(color=MUTED, size=10, family=FONT_FAMILY),
        hoverlabel=dict(
            bgcolor=PANEL,
            bordercolor="rgba(116,134,151,.35)",
            font=dict(color=TEXT, family=FONT_FAMILY, size=11),
        ),
        newshape=dict(line_color="#E7EEF5", line_width=1.2),
    )

    axis = _axis_style()
    fig.update_xaxes(**axis, showgrid=False, rangeslider_visible=False)
    fig.update_yaxes(**axis, side="right")
    fig.update_yaxes(range=[0, 100], row=3, col=1)
    fig.update_yaxes(title_text="거래량", row=2, col=1, title_font=dict(size=9, color=MUTED))
    fig.update_yaxes(title_text="STO", row=3, col=1, title_font=dict(size=9, color=MUTED))
    return fig


def build_pattern_compare_chart(
    current: pd.DataFrame,
    historical: pd.DataFrame,
    current_label: str,
    historical_label: str,
    *,
    height: int = 420,
) -> go.Figure:
    current_values = (current["Close"].astype(float) / float(current.iloc[0]["Close"]) - 1) * 100
    historical_values = (historical["close"].astype(float) / float(historical.iloc[0]["close"]) - 1) * 100

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            y=current_values,
            mode="lines",
            name=f"현재 {current_label}",
            line=dict(width=2.6, color=STO_K),
            hovertemplate="현재 %{y:+.2f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            y=historical_values,
            mode="lines",
            name=f"과거 {historical_label}",
            line=dict(width=1.9, dash="dot", color=UP),
            hovertemplate="과거 %{y:+.2f}%<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color="rgba(116,134,151,.55)", line_width=1)
    fig.update_layout(
        height=height,
        margin=dict(l=12, r=58, t=34, b=14),
        hovermode="x unified",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        legend=dict(
            orientation="h",
            y=1.03,
            x=1,
            xanchor="right",
            bgcolor="rgba(16,24,33,.78)",
            bordercolor="rgba(116,134,151,.22)",
            borderwidth=1,
            font=dict(size=10, family=FONT_FAMILY, color=TEXT),
        ),
        yaxis_title="등락률(%)",
        font=dict(color=MUTED, size=10, family=FONT_FAMILY),
        hoverlabel=dict(
            bgcolor=PANEL,
            bordercolor="rgba(116,134,151,.35)",
            font=dict(color=TEXT, family=FONT_FAMILY, size=11),
        ),
    )
    fig.update_xaxes(**_axis_style())
    fig.update_yaxes(**_axis_style(), side="right")
    return fig
