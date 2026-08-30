from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from collector.base import CollectorRequest
from collector.fdr import FDRCollector
from replay_target.integrated import IntegratedWatchConfig
from replay_target.kis_history import load_reference_history


_MA_WINDOWS = (5, 10, 20, 60, 120, 200)
_MA_COLORS = {
    5: "#22c55e",
    10: "#60a5fa",
    20: "#ef4444",
    60: "#1d4ed8",
    120: "#7c3aed",
    200: "#f97316",
}


def load_replay_chart_frames(
    cfg: IntegratedWatchConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str, str | None]:
    """Load the current and historical frames used by the HTS-style comparison."""

    current_result = FDRCollector().fetch(
        CollectorRequest(market="kr", ticker=cfg.ticker, period=cfg.current_period, interval="1d")
    )
    current = _normalize(current_result.data)

    reference, reference_source, reference_error = load_reference_history(cfg)
    reference = _normalize(reference)
    return current, reference, current_result.source, reference_source, reference_error


def build_hts_figure(
    frame: pd.DataFrame,
    *,
    title: str,
    display_start: str | pd.Timestamp | None = None,
    display_end: str | pd.Timestamp | None = None,
    anchor_date: str | None = None,
    anchor_label: str = "T0",
    target_date: str | None = None,
    target_window_start: str | None = None,
    target_window_end: str | None = None,
) -> go.Figure:
    """Create one HTS-style price + 3-layer stochastic figure."""

    data = _with_indicators(_normalize(frame))
    if data.empty:
        return _empty_figure(title)

    view = data.copy()
    if display_start:
        view = view[view["Date"] >= pd.Timestamp(display_start)]
    if display_end:
        view = view[view["Date"] <= pd.Timestamp(display_end)]
    if view.empty:
        view = data.tail(90).copy()

    figure = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=[0.52, 0.16, 0.16, 0.16],
        subplot_titles=("", "STO 5·3·3", "STO 10·6·6", "STO 20·12·12"),
    )

    figure.add_trace(
        go.Candlestick(
            x=view["Date"],
            open=view["Open"],
            high=view["High"],
            low=view["Low"],
            close=view["Close"],
            name="가격",
            increasing_line_color="#ef4444",
            increasing_fillcolor="#ef4444",
            decreasing_line_color="#2563eb",
            decreasing_fillcolor="#2563eb",
            whiskerwidth=0.2,
            hovertext=[
                f"{d:%Y-%m-%d}<br>시 {o:,.0f} / 고 {h:,.0f}<br>저 {l:,.0f} / 종 {c:,.0f}"
                for d, o, h, l, c in zip(
                    view["Date"], view["Open"], view["High"], view["Low"], view["Close"]
                )
            ],
            hoverinfo="text",
        ),
        row=1,
        col=1,
    )

    for window in _MA_WINDOWS:
        column = f"MA{window}"
        if column not in view.columns or not view[column].notna().any():
            continue
        figure.add_trace(
            go.Scatter(
                x=view["Date"],
                y=view[column],
                mode="lines",
                name=f"MA{window}",
                line={"width": 1.35, "color": _MA_COLORS[window]},
                hovertemplate=f"MA{window} %{{y:,.0f}}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    _add_stochastic_panel(figure, view, "S533_K", "S533_D", row=2)
    _add_stochastic_panel(figure, view, "S1066_K", "S1066_D", row=3)
    _add_stochastic_panel(figure, view, "S201212_K", "S201212_D", row=4)

    if target_window_start and target_window_end:
        try:
            x0 = pd.Timestamp(target_window_start)
            x1 = pd.Timestamp(target_window_end)
            figure.add_vrect(
                x0=x0,
                x1=x1,
                line_width=1.5,
                line_color="#dc2626",
                fillcolor="rgba(220,38,38,0.05)",
                row=1,
                col=1,
            )
        except Exception:
            pass

    _add_marker(figure, anchor_date, anchor_label, "#dc2626")
    _add_marker(figure, target_date, "B Target", "#b91c1c")

    for row in (2, 3, 4):
        figure.add_hline(y=80, line_width=1, line_color="#e879f9", row=row, col=1)
        figure.add_hline(y=20, line_width=1, line_color="#e879f9", row=row, col=1)
        figure.update_yaxes(range=[0, 100], tickvals=[0, 20, 50, 80, 100], row=row, col=1)

    figure.update_yaxes(side="right", tickformat=",.0f", row=1, col=1)
    figure.update_xaxes(
        rangeslider_visible=False,
        showgrid=True,
        gridcolor="rgba(148,163,184,.16)",
        rangebreaks=[{"bounds": ["sat", "mon"]}],
    )
    figure.update_layout(
        title={"text": title, "x": 0.01, "xanchor": "left", "font": {"size": 16}},
        height=760,
        margin={"l": 8, "r": 46, "t": 52, "b": 28},
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"family": "Arial, sans-serif", "size": 10, "color": "#374151"},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.005,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 9},
        },
        hovermode="x unified",
        showlegend=True,
    )
    return figure


def render_hts_comparison(
    st: Any,
    *,
    cfg: IntegratedWatchConfig,
    resolved_reference_anchor_date: str | None,
    resolved_reference_target_date: str | None,
) -> None:
    """Render side-by-side KODEX vs AK HTS-style charts."""

    try:
        current, reference, current_source, reference_source, reference_error = load_replay_chart_frames(cfg)
    except Exception as exc:
        st.caption(f"HTS형 비교차트 데이터 로드 실패: {exc}")
        return

    if current.empty:
        st.caption("KODEX 비교차트용 일봉이 없습니다.")
        return
    if reference.empty:
        detail = f" · {reference_error}" if reference_error else ""
        st.caption(f"AK 2011 비교차트용 일봉이 없습니다{detail}")
        return

    current_anchor = pd.Timestamp(cfg.current_anchor_date)
    current_start = max(current["Date"].min(), current_anchor - pd.Timedelta(days=105))
    current_end = current["Date"].max()

    reference_start = pd.Timestamp(cfg.reference_window_start) - pd.Timedelta(days=45)
    reference_end = max(
        pd.Timestamp(cfg.reference_target_window_end) + pd.Timedelta(days=45),
        pd.Timestamp(resolved_reference_target_date)
        if resolved_reference_target_date
        else pd.Timestamp(cfg.reference_target_window_end) + pd.Timedelta(days=45),
    )

    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            build_hts_figure(
                current,
                title=f"{cfg.symbol} · 현재 경로",
                display_start=current_start,
                display_end=current_end,
                anchor_date=cfg.current_anchor_date,
                anchor_label="현재 T0",
            ),
            use_container_width=True,
            config={"displaylogo": False, "responsive": True, "scrollZoom": True},
            key="replay_hts_current",
        )
        st.caption(f"현재 일봉: {current_source} · T0 {cfg.current_anchor_date}")

    with right:
        st.plotly_chart(
            build_hts_figure(
                reference,
                title=f"{cfg.reference_symbol} · 2011 기준 경로",
                display_start=reference_start,
                display_end=reference_end,
                anchor_date=resolved_reference_anchor_date,
                anchor_label="AK 대응 T0",
                target_date=resolved_reference_target_date,
                target_window_start=cfg.reference_target_window_start,
                target_window_end=cfg.reference_target_window_end,
            ),
            use_container_width=True,
            config={"displaylogo": False, "responsive": True, "scrollZoom": True},
            key="replay_hts_reference",
        )
        source_note = f"과거 일봉: {reference_source}"
        if reference_error:
            source_note += f" · {reference_error}"
        st.caption(source_note)

    st.caption(
        "차트는 사용자가 제공한 HTS 화면처럼 일봉 캔들 + 이동평균 + STO 5·3·3 / 10·6·6 / "
        "20·12·12를 나란히 보여줍니다. Target/Path 점수 산식은 기존 ADE 엔진을 그대로 사용합니다."
    )


def _add_marker(
    figure: go.Figure,
    date_value: str | None,
    label: str,
    color: str,
) -> None:
    if not date_value:
        return
    try:
        x = pd.Timestamp(date_value)
    except Exception:
        return
    figure.add_vline(x=x, line_width=1.3, line_dash="dash", line_color=color, row=1, col=1)
    figure.add_annotation(
        x=x,
        y=1,
        yref="y domain",
        text=label,
        showarrow=False,
        bgcolor="rgba(255,255,255,.86)",
        bordercolor=color,
        borderwidth=1,
        font={"size": 9, "color": color},
        yshift=-10,
        row=1,
        col=1,
    )


def _add_stochastic_panel(
    figure: go.Figure,
    view: pd.DataFrame,
    k_col: str,
    d_col: str,
    *,
    row: int,
) -> None:
    figure.add_trace(
        go.Scatter(
            x=view["Date"],
            y=view[k_col],
            mode="lines",
            name=f"{k_col.replace('_K', '')} %K",
            line={"color": "#f59e0b", "width": 1.25},
            hovertemplate="%K %{y:.1f}<extra></extra>",
            showlegend=False,
        ),
        row=row,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=view["Date"],
            y=view[d_col],
            mode="lines",
            name=f"{d_col.replace('_D', '')} %D",
            line={"color": "#3b82f6", "width": 1.25},
            hovertemplate="%D %{y:.1f}<extra></extra>",
            showlegend=False,
        ),
        row=row,
        col=1,
    )


def _with_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    data = frame.copy()
    for window in _MA_WINDOWS:
        data[f"MA{window}"] = data["Close"].rolling(window, min_periods=1).mean()

    for n, smooth_k, smooth_d, prefix in (
        (5, 3, 3, "S533"),
        (10, 6, 6, "S1066"),
        (20, 12, 12, "S201212"),
    ):
        low_n = data["Low"].rolling(n, min_periods=n).min()
        high_n = data["High"].rolling(n, min_periods=n).max()
        span = (high_n - low_n).replace(0, pd.NA)
        raw = (data["Close"] - low_n) / span * 100.0
        k = raw.rolling(smooth_k, min_periods=1).mean()
        d = k.rolling(smooth_d, min_periods=1).mean()
        data[f"{prefix}_K"] = pd.to_numeric(k, errors="coerce")
        data[f"{prefix}_D"] = pd.to_numeric(d, errors="coerce")
    return data


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]
    data = data.rename(
        columns={
            "trade_date": "Date",
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    if "Date" not in data.columns:
        data = data.reset_index()
        if "Date" not in data.columns and "index" in data.columns:
            data = data.rename(columns={"index": "Date"})
    required = ["Date", "Open", "High", "Low", "Close"]
    if not all(column in data.columns for column in required):
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    if "Volume" not in data.columns:
        data["Volume"] = 0.0
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    for column in ("Open", "High", "Low", "Close", "Volume"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return (
        data[["Date", "Open", "High", "Low", "Close", "Volume"]]
        .dropna(subset=["Date", "Open", "High", "Low", "Close"])
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )


def _empty_figure(title: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text="차트 데이터 없음",
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
    )
    figure.update_layout(title=title, height=420, paper_bgcolor="white", plot_bgcolor="white")
    return figure
