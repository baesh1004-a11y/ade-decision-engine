from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


CHART_CONFIG = {"displayModeBar": True, "scrollZoom": True, "responsive": True}


def stochastic_ohlc(df: pd.DataFrame, period: int = 14, smooth: int = 3):
    lowest = df["Low"].rolling(period, min_periods=1).min()
    highest = df["High"].rolling(period, min_periods=1).max()
    k = ((df["Close"] - lowest) / (highest - lowest).replace(0, 1) * 100).fillna(50)
    d = k.rolling(smooth, min_periods=1).mean()
    return k, d


def build_trading_chart(data: pd.DataFrame, title: str, *, height: int = 520) -> go.Figure:
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
        vertical_spacing=0.025,
        row_heights=[0.62, 0.16, 0.22],
    )
    fig.add_trace(
        go.Candlestick(
            x=df["Date"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            name=title,
            increasing_line_color="#DC2626", increasing_fillcolor="#DC2626",
            decreasing_line_color="#2563EB", decreasing_fillcolor="#2563EB",
        ),
        row=1, col=1,
    )
    fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_UPPER"], name="BB 상단", line=dict(color="#C76B00", width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["SMA20"], name="SMA20", line=dict(color="#1E3A8A", width=1.8)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=df["BB_LOWER"], name="BB 하단", line=dict(color="#64748B", width=1.2), fill="tonexty", fillcolor="rgba(100,116,139,.04)"), row=1, col=1)

    volume_colors = ["rgba(220,38,38,.42)" if close >= open_ else "rgba(37,99,235,.42)" for close, open_ in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df["Date"], y=df["Volume"], name="거래량", marker_color=volume_colors), row=2, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=k, name="STO %K", line=dict(color="#1E3A8A", width=1.7)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df["Date"], y=d, name="STO %D", line=dict(color="#C76B00", width=1.7)), row=3, col=1)
    fig.add_hline(y=80, line_dash="dash", line_color="#8d99a6", row=3, col=1)
    fig.add_hline(y=20, line_dash="dash", line_color="#8d99a6", row=3, col=1)

    fig.update_layout(
        height=height,
        margin=dict(l=6, r=44, t=30, b=6),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(255,255,255,.7)"),
        font=dict(color="#64748B", size=12, family="Pretendard, Malgun Gothic, Arial, sans-serif"),
    )
    fig.update_xaxes(showgrid=False, rangeslider_visible=False)
    fig.update_yaxes(showgrid=True, gridcolor="#E5E7EB", side="right")
    fig.update_yaxes(range=[0, 100], row=3, col=1)
    return fig


def build_pattern_compare_chart(
    current: pd.DataFrame,
    historical: pd.DataFrame,
    current_label: str,
    historical_label: str,
) -> go.Figure:
    current_values = (current["Close"].astype(float) / float(current.iloc[0]["Close"]) - 1) * 100
    historical_values = (historical["close"].astype(float) / float(historical.iloc[0]["close"]) - 1) * 100
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=current_values, mode="lines", name=f"현재 {current_label}", line=dict(width=3, color="#2962ff")))
    fig.add_trace(go.Scatter(y=historical_values, mode="lines", name=f"과거 {historical_label}", line=dict(width=2, dash="dot", color="#ef5350")))
    fig.add_hline(y=0, line_color="#8d99a6", line_width=1)
    fig.update_layout(
        height=700,
        margin=dict(l=15, r=55, t=35, b=20),
        hovermode="x unified",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend=dict(orientation="h", y=1.04),
        yaxis_title="등락률(%)",
        font=dict(color="#22364a", size=11),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(150,165,180,.16)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(150,165,180,.16)", side="right")
    return fig
