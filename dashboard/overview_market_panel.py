from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.economic_calendar_service import load_economic_calendar
from dashboard.market_overview_service import load_market_overview, load_sector_strength
from markets.profiles import get_market_profile


def _event_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    preferred = ["일시(KST)", "국가", "구분", "이벤트", "중요도", "출처", "비고"]
    return frame[[column for column in preferred if column in frame.columns]]


def _render_market_metrics(refresh: bool) -> None:
    metrics, warning = load_market_overview(refresh=refresh)
    ordered = ["kospi", "kosdaq", "sp500", "nasdaq", "usdkrw", "vix"]
    columns = st.columns(6)
    for column, key in zip(columns, ordered):
        metric = metrics.get(key)
        if metric is None or metric.value is None:
            column.metric(metric.label if metric else key.upper(), "조회 실패")
            continue
        value = f"{metric.value:,.2f}"
        delta = f"{metric.change_rate:+.2f}%" if metric.change_rate is not None else None
        column.metric(metric.label, value, delta)
    if warning:
        st.caption(warning)


def _render_key_events(refresh: bool) -> None:
    rows, warning = load_economic_calendar(days_ahead=90, refresh=refresh)
    important = [row for row in rows if str(row.get("중요도") or "") in {"높음", "매우 높음"}]
    st.markdown("#### 주요 이벤트")
    if important:
        st.dataframe(_event_frame(important[:5]), hide_index=True, use_container_width=True)
    else:
        st.info("표시할 주요 이벤트가 없습니다.")
    if warning:
        st.caption(warning)
    if st.button("주요 이벤트 상세보기", key="overview_event_details", use_container_width=True):
        st.session_state.ade_event_details_open = not bool(st.session_state.get("ade_event_details_open", False))
        st.rerun()
    if st.session_state.get("ade_event_details_open"):
        st.markdown("##### 향후 90일 전체 일정")
        if rows:
            st.dataframe(_event_frame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("표시할 전체 이벤트가 없습니다.")


def _render_sector_ranking(refresh: bool) -> None:
    st.markdown("#### 국내 업종 등락 순위")
    rows, warning = load_sector_strength(get_market_profile("kr").db_path, limit=10, refresh=refresh)
    if rows:
        frame = pd.DataFrame(rows)
        display = pd.DataFrame(
            {
                "업종": frame.get("sector"),
                "등락률(%)": frame.get("change_rate"),
                "거래대금": frame.get("turnover"),
                "기준일": frame.get("as_of"),
                "출처": frame.get("source"),
            }
        )
        st.dataframe(display, hide_index=True, use_container_width=True)
    else:
        st.info("국내 업종 등락 데이터를 아직 가져오지 못했습니다. 잠시 후 다시 시도합니다.")
    if warning:
        st.caption(warning)


def render_market_overview_panel() -> None:
    st.markdown("### 시장의 현재 정보")
    refresh = st.button("시장 데이터 새로고침", key="overview_market_refresh", use_container_width=True)
    _render_market_metrics(refresh)
    _render_key_events(refresh)
    _render_sector_ranking(refresh)
