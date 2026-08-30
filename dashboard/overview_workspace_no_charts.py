from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard import overview_workspace as base


def _render_market_strip_without_charts(metrics: dict[str, Any]) -> None:
    """Render market KPI cards with no history/SVG/sparkline markup at all."""

    ordered = ["kospi", "kosdaq", "sp500", "nasdaq", "usdkrw", "vix"]
    cards: list[str] = []
    for key in ordered:
        label, value, change, change_rate, tone = base._metric_parts(metrics, key)
        arrow = "▲" if tone == "up" else ("▼" if tone == "down" else "•")
        points = f"{change:+,.2f}" if value != "조회 실패" else "-"
        delta = f"{change_rate:+.2f}%" if value != "조회 실패" else "-"
        cards.append(
            f'<div class="ade-index-card {tone}">'
            f'<div class="label">{label} · 실시간</div>'
            f'<div class="value">{value}</div>'
            f'<div class="move"><div class="points">{arrow} {points}</div>'
            f'<div class="delta">({delta})</div></div></div>'
        )
    st.markdown(
        '<div class="ade-market-strip"><div class="ade-index-grid">'
        + "".join(cards)
        + "</div></div>",
        unsafe_allow_html=True,
    )


def render_overview_workspace(base_app: Any) -> None:
    """Use the existing situation board while physically omitting mini charts."""

    st.markdown(
        """
        <style>
        .ade-index-card{min-height:0!important;padding:17px 18px!important}
        .ade-index-card .value{margin-top:6px!important}
        .ade-index-card .move{margin-top:6px!important}
        </style>
        """,
        unsafe_allow_html=True,
    )
    original = base._render_market_strip
    base._render_market_strip = _render_market_strip_without_charts
    try:
        base.render_overview_workspace(base_app)
    finally:
        base._render_market_strip = original
