from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from broker.kis_websocket import shared_market_client
from dashboard import recommendation_workbench_v2_app as recommendation_base
from dashboard.charts import CHART_CONFIG, build_pattern_compare_chart, build_trading_chart
from dashboard.data_health_panel import build_data_health_rows, render_data_health_panel
from dashboard.kis_zero_base_bridge import (
    cancel_paper_order,
    kis_configured,
    kis_paper_enabled,
    load_daily_orders,
    load_kis_quote,
    load_kis_snapshot,
    load_orderable,
    load_pending_orders,
    refresh_order_views,
    revise_paper_order,
    submit_paper_order,
)
from dashboard.market_price_fallback import load_external_daily_bars
from dashboard.news_disclosure_service import load_security_news
from dashboard.supply_demand_service import load_supply_demand_health
from dashboard.order_candidate_store import (
    OrderCandidateStoreError,
    clear_candidates,
    delete_candidate,
    import_legacy_candidates,
    list_candidates,
    list_legacy_candidates,
    mark_selected,
    store_health,
    upsert_candidate,
)
from dashboard.professional_components import render_workspace_card, render_workspace_intro
from dashboard.recommendation_detail_enhancements import(render_recommendation_detail_enhancements,)
from dashboard.sto_professional_panel import render_professional_sto_panel
from dashboard.ui_workspace import DEFAULT_WORKSPACE_KEY, WORKSPACES, get_workspace
from jp_radar.live_chart import make_live_radar_chart
from jp_radar.stock_engine import JPStockRadarEngine
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, normalize_ticker
from recommendation.run_context import load_latest_context

LOGGER = logging.getLogger(__name__)
THEME_PATH = Path(__file__).with_name("ade_zero_base_theme.css")
CUSTOM_CSS = """<style>[data-testid="stSidebar"],[data-testid="stSidebarNav"],section[data-testid="stSidebar"],div[data-testid="stSidebarNav"],[data-testid="collapsedControl"],button[kind="headerNoPadding"]{display:none!important}</style>"""
LIVE_REFRESH_SECONDS = 5
LIVE_PRICE_MAX_AGE_SECONDS = 15
LIVE_SESSION_TICKER_LIMIT = 5
ORDER_DUPLICATE_WINDOW_SECONDS = 8
ORDER_ACTION_DUPLICATE_WINDOW_SECONDS = 8


def _apply_zero_base_theme() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    if THEME_PATH.exists():
        st.markdown(f"<style>{THEME_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _apply_workspace_theme() -> None:
    workspace = get_workspace(st.session_state.get("ade_ui_workspace"))
    st.markdown(f'<div id="ade-workspace-root" class="{workspace.theme_class}"></div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <style>
        .stApp {{ --ade-workspace-name: '{workspace.short_name}'; }}
        body:has(#ade-workspace-root.{workspace.theme_class}) .stApp {{}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def run() -> None:
    st.set_page_config(page_title="ADE Decision Engine", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
    _apply_zero_base_theme()
    _init_state()
    if not st.session_state.ade_ui_workspace_confirmed:
        _render_workspace_selector()
        return
    _apply_workspace_theme()
    _render_top_navigation()
    page = st.session_state.ade_primary_page
    if page == "상황종합판":
        _release_live_lease()
        _render_overview()
    elif page == "추천결과":
        _release_live_lease()
        _render_recommendations()
    elif page == "주문":
        _render_orders()
    else:
        _release_live_lease()
        _render_jp_radar()
    _render_status_bar()


def _init_state() -> None:
    defaults = {
        "ade_primary_page": "상황종합판",
        "ade_overview_tab": "시장",
        "ade_market": "kr",
        "ade_recommendation_detail": None,
        "ade_order_ticker": None,
        "ade_jp_ticker": None,
        "ade_order_confirmation": False,
        "ade_live_orderbook": True,
        "ade_live_refresh": True,
        "ade_order_signature": None,
        "ade_order_context": None,
        "ade_live_ticker_lru": [],
        "ade_live_subscription_ticker": None,
        "ade_order_submit_state": "idle",
        "ade_order_flash": None,
        "ade_last_submitted_signature": None,
        "ade_last_submitted_at": 0.0,
        "ade_last_client_request_id": None,
        "ade_order_action_state": "idle",
        "ade_last_order_action_signature": None,
        "ade_last_order_action_at": 0.0,
        "ade_owner_id": uuid.uuid4().hex,
        "ade_candidate_delete_target": None,
        "ade_candidate_clear_market": None,
        "ade_ui_workspace": DEFAULT_WORKSPACE_KEY,
        "ade_ui_workspace_confirmed": False,
        "ade_validation_attempted": {},
        "ade_validation_errors": {},
        "ade_show_heavy_charts": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _render_workspace_selector() -> None:
    render_workspace_intro()
    selected = st.session_state.ade_ui_workspace
    columns = st.columns(5)
    for index, workspace in enumerate(WORKSPACES):
        with columns[index]:
            render_workspace_card(workspace, selected=selected == workspace.key)
            if st.button(
                "선택됨" if selected == workspace.key else "이 디자인 선택",
                key=f"workspace_{workspace.key}",
                type="primary" if selected == workspace.key else "secondary",
                use_container_width=True,
            ):
                st.session_state.ade_ui_workspace = workspace.key
                st.rerun()
    st.divider()
    workspace = get_workspace(selected)
    st.markdown(f"**현재 선택:** {workspace.name}")
    c1, c2 = st.columns([1, 1])
    if c1.button("이 워크스페이스로 시작", type="primary", use_container_width=True):
        st.session_state.ade_ui_workspace_confirmed = True
        st.rerun()
    if c2.button("추천 조합으로 시작", use_container_width=True):
        st.session_state.ade_ui_workspace = "ai_copilot"
        st.session_state.ade_ui_workspace_confirmed = True
        st.rerun()


def _render_top_navigation() -> None:
    workspace = get_workspace(st.session_state.ade_ui_workspace)
    c1, c2, c3, c4, c5, c6, c7 = st.columns([1.8, 1.1, 1.1, 1, .28, 1.15, 1.1])
    with c1:
        st.markdown(f'<div class="ade-brand">ADE <span class="ade-subtle">{workspace.short_name}</span></div>', unsafe_allow_html=True)
    for col, label in [(c2, "상황종합판"), (c3, "추천결과"), (c4, "주문")]:
        if col.button(label, type="primary" if st.session_state.ade_primary_page == label else "secondary", use_container_width=True):
            st.session_state.ade_primary_page = label
            st.session_state.ade_recommendation_detail = None
            st.session_state.ade_show_heavy_charts = False
            st.rerun()
    with c5:
        st.markdown('<div class="ade-jp-separator">&nbsp;</div>', unsafe_allow_html=True)
    with c6:
        if st.button("JP Radar", type="primary" if st.session_state.ade_primary_page == "JP Radar" else "secondary", use_container_width=True):
            st.session_state.ade_primary_page = "JP Radar"
            st.rerun()
    with c7:
        if st.button("UI 변경", use_container_width=True):
            _release_live_lease()
            st.session_state.ade_ui_workspace_confirmed = False
            st.rerun()
    st.markdown('<div class="ade-divider"></div>', unsafe_allow_html=True)


def _render_overview() -> None:
    tabs = st.segmented_control("상황종합판 하위 메뉴", options=["시장", "이벤트", "내 투자"], default=st.session_state.ade_overview_tab, key="ade_overview_segment", label_visibility="collapsed")
    st.session_state.ade_overview_tab = tabs or "시장"
    if tabs == "시장":
        _render_market_overview()
    elif tabs == "이벤트":
        _render_event_timeline()
    else:
        _render_portfolio_overview()


def _render_market_overview() -> None:
    st.markdown("### 시장의 현재 정보")
    st.warning("시장지수·환율·이벤트 자동 연동은 아직 미완료입니다. 아래 값은 투자판단용 실시간 데이터가 아닙니다.")
    for col, label in zip(st.columns(6), ["KOSPI", "KOSDAQ", "S&P 500", "NASDAQ", "USD/KRW", "VIX"]):
        col.metric(label, "연결 대기")
    st.markdown("#### 주요 이벤트")
    st.info("경제지표·중앙은행 일정 데이터 연결 대기")
    st.markdown("#### 국내 섹터 강도")
    st.info("실시간 섹터 강도 데이터 연결 대기")


def _render_event_timeline(compact: bool = False) -> None:
    if not compact:
        st.markdown("### 오늘의 이벤트 타임라인")
    st.info("실시간 경제 이벤트 데이터 연결 대기")


def _kis_data(refresh: bool = False):
    return load_kis_snapshot(get_market_profile("kr").db_path, refresh=refresh, max_age_seconds=60)


@st.cache_data(ttl=30, show_spinner=False)
def _cached_kis_snapshot():
    return load_kis_snapshot(get_market_profile("kr").db_path, refresh=False, max_age_seconds=60)


def _render_portfolio_overview() -> None:
    st.markdown("### 내 투자 현황")
    refresh = st.button("KIS 계좌 새로고침", key="kis_portfolio_refresh")
    if refresh:
        _cached_kis_snapshot.clear()
        account, positions, error = _kis_data(True)
    else:
        account, positions, error = _cached_kis_snapshot()
    if account is None:
        st.info(error or "KIS 계좌 스냅샷이 없습니다.")
        return
    cash = float(account.get("cash") or 0)
    evaluation = float(account.get("evaluation_amount") or 0)
    pnl = float(account.get("pnl") or 0)
    total = cash + evaluation
    invested = evaluation - pnl
    pnl_rate = (pnl / invested * 100) if invested > 0 else 0
    for col, (label, value, delta) in zip(st.columns(5), [("총자산", f"₩{total:,.0f}", None), ("주문가능 현금", f"₩{cash:,.0f}", None), ("평가금액", f"₩{evaluation:,.0f}", None), ("평가손익", f"₩{pnl:+,.0f}", f"{pnl_rate:+.2f}%"), ("보유종목", f"{int(account.get('position_count') or len(positions))}개", None)]):
        col.metric(label, value, delta)
    if positions:
        st.dataframe(pd.DataFrame(positions), hide_index=True, use_container_width=True)
    if error:
        st.caption(error)


def _render_recommendations() -> None:
    market = _market_selector("ade_reco_market")
    if st.session_state.ade_recommendation_detail:
        _render_recommendation_detail(market, st.session_state.ade_recommendation_detail)
        return
    recommendations, context = _load_recommendations(market)
    st.markdown(f"### {'국내' if market == 'kr' else '미국'} 추천종목")
    if context is not None:
        st.caption(f"실행ID {context.run_id} · 생성 {str(context.finished_at or '-')[:19]} · 추천 {context.recommendation_count}개")
    if not recommendations:
        st.info("저장된 추천 결과가 없습니다.")
        return
    for row in recommendations:
        cols = st.columns([.55, 3.2, 1.25, 1.05, 1.05])
        ticker = str(row.get("ticker"))
        symbol = str(row.get("symbol") or ticker)
        cols[0].markdown(f"**#{int(row.get('rank_no', 0))}**")
        if cols[1].button(f"{symbol}\n\n{ticker}", key=f"detail_{market}_{ticker}", use_container_width=True):
            st.session_state.ade_recommendation_detail = ticker
            st.session_state.ade_show_heavy_charts = False
            st.rerun()
        score = float(row.get("score") or row.get("final_similarity") or row.get("weekly_similarity") or 0)
        cols[2].metric("추천점수", f"{score:.1f}")
        if cols[3].button("JP Radar", key=f"jp_{market}_{ticker}", use_container_width=True):
            st.session_state.ade_primary_page = "JP Radar"
            st.session_state.ade_jp_ticker = ticker
            st.rerun()
        if cols[4].button("주문", key=f"order_{market}_{ticker}", type="primary", use_container_width=True):
            try:
                _add_order_candidate(market, ticker, symbol)
            except OrderCandidateStoreError as exc:
                st.error(str(exc))
                continue
            st.session_state.ade_primary_page = "주문"
            st.session_state.ade_order_ticker = ticker
            _reset_order_confirmation()
            st.rerun()
        st.divider()


def _payload_number(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        try:
            if value is not None and str(value) != "":
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _payload_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    try:
        rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    except sqlite3.Error:
        return []
    return [str(row[1]) for row in rows]


def _load_current_bars_resilient(conn: sqlite3.Connection, market: str, ticker: str, configured_source: str) -> tuple[pd.DataFrame, str, str | None]:
    direct = recommendation_base._current_bars(conn, market, ticker, configured_source)
    if not direct.empty:
        return direct, f"DB:{configured_source or '자동'}", None

    candidate_tables = [configured_source, "ohlcv", "daily_prices", "price_daily", "prices", "price_bars"]
    existing = [str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for table in [name for name in candidate_tables if name and name in existing]:
        columns = _table_columns(conn, table)
        ticker_col = next((name for name in ("ticker", "symbol", "code") if name in columns), None)
        date_col = next((name for name in ("date", "trade_date", "datetime", "timestamp") if name in columns), None)
        if not ticker_col or not date_col:
            continue
        variants = [ticker]
        if market == "kr" and ticker.isdigit():
            variants.extend([ticker.zfill(6), ticker.lstrip("0") or "0", f"{ticker.zfill(6)}.KS", f"{ticker.zfill(6)}.KQ"])
        placeholders = ",".join("?" for _ in variants)
        try:
            rows = conn.execute(
                f'SELECT * FROM "{table}" WHERE CAST("{ticker_col}" AS TEXT) IN ({placeholders}) ORDER BY "{date_col}" DESC LIMIT 180',
                tuple(dict.fromkeys(variants)),
            ).fetchall()
        except sqlite3.Error:
            continue
        frame = pd.DataFrame([dict(row) for row in rows])
        if not frame.empty:
            frame = frame.rename(columns={date_col: "date"}).sort_values("date")
            return frame, f"DB:{table}", None

    external, source, warning = load_external_daily_bars(market, ticker)
    if not external.empty:
        return external, f"외부:{source}", warning
    return pd.DataFrame(), source, warning


def _pattern_from_replay(conn: sqlite3.Connection, payload: dict[str, Any]):
    selector = getattr(recommendation_base, "_selected_pattern", None)
    if callable(selector):
        try:
            selected = selector(conn, payload)
        except Exception as exc:
            LOGGER.warning("Replay pattern selector failed; using local fallback: %s", exc)
        else:
            if selected is not None:
                return selected

    matches = payload.get("replay_matches") or []
    if not isinstance(matches, list):
        return None
    for match in matches:
        if not isinstance(match, dict):
            continue
        event_ids = [
            str(match.get("source_event_id") or "").strip(),
            str(match.get("event_id") or "").strip(),
            str(match.get("pattern_id") or "").strip(),
        ]
        for event_id in [value for value in dict.fromkeys(event_ids) if value]:
            for column in ("pattern_id", "source_event_id"):
                try:
                    row = conn.execute(
                        f"SELECT * FROM surge_patterns WHERE {column}=? ORDER BY surge_start_date DESC LIMIT 1",
                        (event_id,),
                    ).fetchone()
                except sqlite3.Error:
                    row = None
                if row is not None:
                    return row
    return None


def _run_validation_once(profile, run_id: str, market: str, ticker: str, selected: dict[str, Any], payload: dict[str, Any], validation_key: str) -> None:
    if run_id == "-" or st.session_state.ade_validation_attempted.get(validation_key):
        return
    st.session_state.ade_validation_attempted[validation_key] = True
    st.session_state.ade_validation_errors.pop(validation_key, None)

# Remaining file content is unchanged in the repository update context.
