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


def _render_portfolio_overview() -> None:
    st.markdown("### 내 투자 현황")
    account, positions, error = _kis_data(refresh=st.button("KIS 계좌 새로고침", key="kis_portfolio_refresh"))
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
    selected = recommendation_base._selected_pattern(conn, payload)
    if selected is not None:
        return selected
    matches = payload.get("replay_matches") or []
    if not isinstance(matches, list):
        return None
    for match in matches:
        if not isinstance(match, dict):
            continue
        event_id = str(match.get("event_id") or match.get("pattern_id") or "").strip()
        if not event_id:
            continue
        for column in ("pattern_id", "source_event_id"):
            try:
                row = conn.execute(f"SELECT * FROM surge_patterns WHERE {column}=? ORDER BY surge_start_date DESC LIMIT 1", (event_id,)).fetchone()
            except sqlite3.Error:
                row = None
            if row is not None:
                return row
    return None


def _render_recommendation_detail(market: str, ticker: str) -> None:
    if st.button("← 추천종목으로 돌아가기"):
        st.session_state.ade_recommendation_detail = None
        st.rerun()
    recommendations, context = _load_recommendations(market)
    selected = next((r for r in recommendations if str(r.get("ticker")) == ticker), None)
    if selected is None:
        st.warning("선택 종목을 찾을 수 없습니다.")
        return
    profile = get_market_profile(market)
    payload = _safe_json(selected.get("payload_json"))
    validation = context.validations.get(normalize_ticker(ticker, market)) if context else None
    with sqlite3.connect(str(profile.db_path), timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        pattern = _pattern_from_replay(conn, payload)
        current, current_source, current_warning = _load_current_bars_resilient(conn, market, normalize_ticker(ticker, market), profile.price_source)
        historical = recommendation_base._pattern_bars(conn, pattern)
        table_counts = {
            "surge_patterns": conn.execute("SELECT COUNT(*) FROM surge_patterns").fetchone()[0] if recommendation_base._table_exists(conn, "surge_patterns") else 0,
            "surge_pattern_bars": conn.execute("SELECT COUNT(*) FROM surge_pattern_bars").fetchone()[0] if recommendation_base._table_exists(conn, "surge_pattern_bars") else 0,
        }

    symbol = str(selected.get("symbol") or selected.get("name") or ticker)
    weekly = float(selected.get("weekly_similarity") or selected.get("score") or selected.get("final_similarity") or 0)
    sto = float(selected.get("sto_similarity") or 0)
    run_id = context.run_id if context else "-"
    finished_at = str(context.finished_at or "-")[:19] if context else "-"
    replay_matches = payload.get("replay_matches") or []
    replay_count = len(replay_matches) if isinstance(replay_matches, list) else 0
    current_end = "-"
    date_column = next((name for name in ("Date", "date", "trade_date") if name in current.columns), None)
    if not current.empty and date_column:
        current_end = str(pd.to_datetime(current[date_column].iloc[-1], errors="coerce"))[:19]

    news_rows, news_warning = load_security_news(ticker, symbol, limit=16)
    news_count = sum(1 for row in news_rows if str(row.get("구분") or "") == "뉴스")
    disclosure_count = sum(1 for row in news_rows if str(row.get("구분") or "") == "공시")

    risk_score = None
    environment_score = None
    if validation is not None:
        row = dict(validation)
        risk_score = float(row.get("risk_score") or 0)
        environment_score = float(row.get("final_score") or row.get("score") or 0)

    target = _payload_number(payload, "target_price", "take_profit", "expected_price")
    stop = _payload_number(payload, "stop_loss", "stop_price")
    confidence = _payload_number(payload, "confidence", "confidence_score")
    summary = _payload_text(payload, "ai_summary", "summary", "reason", "recommendation_reason")

    st.markdown(f"## {symbol}")
    st.caption(f"{ticker} · 실행ID {run_id} · 생성 {finished_at} · 가격기준 {current_end} · 가격소스 {current_source}")
    if current_warning:
        st.caption(f"가격 보조 조회: {current_warning}")

    kpis = st.columns(6)
    kpis[0].metric("추천점수", f"{weekly:.1f}")
    kpis[1].metric("STO 유사도", f"{sto:.1f}%")
    kpis[2].metric("필터", "PASS")
    kpis[3].metric("과거 유사사례", f"{replay_count}건")
    kpis[4].metric("환경점수", f"{environment_score:.1f}" if environment_score is not None else "미측정")
    kpis[5].metric("위험점수", f"{risk_score:.1f}" if risk_score is not None else "미측정")

    st.markdown("### 1. 가격·거래량과 종합 판단")
    if current.empty:
        st.warning("현재 가격·거래량 원본을 찾지 못했습니다. 아래 진단정보로 누락 위치를 확인하세요.")
        st.dataframe(
            pd.DataFrame([
                {"진단": "현재 가격 행", "값": 0},
                {"진단": "가격 조회 소스", "값": current_source},
                {"진단": "가격 보조 조회", "값": current_warning or "오류 정보 없음"},
                {"진단": "Replay 저장 건수", "값": replay_count},
                {"진단": "선택 과거 패턴", "값": "있음" if pattern is not None else "없음"},
                {"진단": "과거 패턴 봉", "값": len(historical)},
                {"진단": "전체 surge_patterns", "값": table_counts["surge_patterns"]},
                {"진단": "전체 surge_pattern_bars", "값": table_counts["surge_pattern_bars"]},
            ]),
            hide_index=True,
            use_container_width=True,
        )
    else:
        main_left, main_right = st.columns([1.55, 1], gap="large")
        with main_left:
            st.plotly_chart(build_trading_chart(current, symbol), use_container_width=True, config=CHART_CONFIG)
        with main_right:
            st.markdown("#### AI 종합판단")
            if summary:
                st.write(summary)
            else:
                st.info("AI 요약 데이터가 아직 저장되지 않았습니다. 저장된 추천·패턴·뉴스 데이터를 기준으로 확인 중입니다.")
            st.dataframe(
                pd.DataFrame([
                    {"항목": "목표가", "값": f"{target:,.0f}" if target is not None else "미산출"},
                    {"항목": "손절가", "값": f"{stop:,.0f}" if stop is not None else "미산출"},
                    {"항목": "신뢰도", "값": f"{confidence:.1f}" if confidence is not None else "미산출"},
                    {"항목": "뉴스", "값": f"{news_count}건"},
                    {"항목": "공시", "값": f"{disclosure_count}건" if disclosure_count else "없음/미설정"},
                ]),
                hide_index=True,
                use_container_width=True,
            )

    st.markdown("### 2. STO 구조와 Replay 패턴 비교")
    if pattern is not None and not historical.empty and not current.empty:
        historical_label = str(pattern["name"] or pattern["ticker"])
        render_professional_sto_panel(
            current=current,
            historical=historical,
            pattern=pattern,
            current_label=symbol,
            historical_label=historical_label,
            stored_similarity=sto,
        )
    else:
        reasons = []
        if current.empty:
            reasons.append("현재 가격 0행")
        if pattern is None:
            reasons.append("선택 과거 패턴 없음")
        if historical.empty:
            reasons.append("과거 패턴 봉 0행")
        st.info("STO/Replay 차트 대기 · " + " · ".join(reasons))
        if isinstance(replay_matches, list) and replay_matches:
            preview_rows = []
            for index, match in enumerate(replay_matches[:10], start=1):
                if not isinstance(match, dict):
                    continue
                preview_rows.append({
                    "순위": index,
                    "종목": match.get("name") or match.get("ticker") or "-",
                    "사례ID": match.get("event_id") or match.get("pattern_id") or "-",
                    "유사도": match.get("similarity") or match.get("score") or "-",
                    "기준일": match.get("date") or match.get("event_date") or "-",
                    "이후수익률": match.get("return") or match.get("forward_return") or "-",
                })
            if preview_rows:
                st.dataframe(pd.DataFrame(preview_rows), hide_index=True, use_container_width=True)

    st.markdown("### 3. 원본 패턴 검증")
    if not current.empty and pattern is not None and not historical.empty:
        compare_left, compare_right = st.columns([1, 1], gap="large")
        with compare_left:
            st.markdown("#### 현재 종목 원본 차트")
            st.plotly_chart(build_trading_chart(current, symbol), use_container_width=True, config=CHART_CONFIG)
        with compare_right:
            historical_label = str(pattern["name"] or pattern["ticker"])
            st.markdown(f"#### 과거 유사사례 · {historical_label}")
            st.plotly_chart(
                build_pattern_compare_chart(current, historical, symbol, historical_label),
                use_container_width=True,
                config=CHART_CONFIG,
            )
    else:
        st.caption("원본 비교 차트는 현재 가격과 과거 패턴 봉이 모두 준비되면 자동 표시됩니다.")

    st.markdown("### 4. 근거·리스크·시장 환경")
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown("#### 추천 근거")
        evidence_rows = [
            {"항목": "주봉 패턴", "값": f"{weekly:.1f}%", "상태": "핵심 순위 근거"},
            {"항목": "STO 필터", "값": f"{sto:.1f}%", "상태": "PASS"},
            {"항목": "과거 유사사례", "값": f"{replay_count}건", "상태": "확인 가능" if replay_count else "없음"},
        ]
        if environment_score is not None:
            evidence_rows.append({"항목": "시장·업종 환경", "값": f"{environment_score:.1f}", "상태": "측정됨"})
        if risk_score is not None:
            evidence_rows.append({"항목": "위험도", "값": f"{risk_score:.1f}", "상태": "낮을수록 유리"})
        st.dataframe(pd.DataFrame(evidence_rows), hide_index=True, use_container_width=True)

        st.markdown("#### 데이터 가용성")
        availability = [
            {"데이터": "현재 가격·거래량", "상태": f"{len(current)}행 · {current_source}" if not current.empty else "없음"},
            {"데이터": "과거 패턴", "상태": f"{len(historical)}행" if not historical.empty and pattern is not None else "없음"},
            {"데이터": "환경 조언", "상태": "있음" if validation is not None else "없음"},
            {"데이터": "뉴스", "상태": f"{news_count}건" if news_count else "없음"},
            {"데이터": "공시", "상태": f"{disclosure_count}건" if disclosure_count else "없음/미설정"},
            {"데이터": "외국인·기관 수급", "상태": "미연결"},
        ]
        st.dataframe(pd.DataFrame(availability), hide_index=True, use_container_width=True)

    with right:
        st.markdown("#### 반대 근거·주의사항")
        cautions = payload.get("risk_factors") or payload.get("cautions") or payload.get("warnings") or []
        if isinstance(cautions, str):
            cautions = [cautions]
        if cautions:
            for item in cautions[:8]:
                st.warning(str(item))
        else:
            st.caption("저장된 반대 근거 데이터가 없습니다. 데이터가 없음을 긍정 신호로 해석하면 안 됩니다.")

        st.markdown("#### 시장·업종 환경 조언")
        if validation is not None:
            st.success("시장·업종 환경 조언이 계산되어 있습니다.")
        else:
            st.caption("추천 순위는 바꾸지 않고, 선택 종목의 시장·업종 환경을 추가 확인합니다.")
            if st.button("환경 조언 계산", key=f"detail_validate_{run_id}_{ticker}", use_container_width=True):
                recommendation_base._run_selected_validation(profile.db_path, run_id, selected, payload)
                st.success("환경 조언을 저장했습니다.")
                st.rerun()

    st.markdown("### 5. 최신 뉴스·공시")
    if news_rows:
        st.dataframe(news_rows, hide_index=True, use_container_width=True)
    else:
        st.info("표시할 최신 뉴스·공시가 없습니다.")
    if news_warning:
        st.caption(news_warning)


def _render_orders() -> None:
    _render_order_flash()
    previous_market = st.session_state.ade_market
    market = _market_selector("ade_order_market")
    if previous_market != market:
        _release_live_lease()
        st.session_state.ade_order_ticker = None
        _reset_order_confirmation()
        _clear_live_session_state()
    st.session_state.ade_market = market
    if st.session_state.ade_order_ticker:
        _render_order_ticket(market, st.session_state.ade_order_ticker)
        return
    _release_live_lease()
    st.markdown("### 주문")
    account, positions, error = _kis_data(refresh=st.button("KIS 계좌 새로고침", key="kis_orders_refresh") if market == "kr" else False) if market == "kr" else (None, [], None)
    tabs = st.tabs(["주문후보", "보유종목", "미체결", "당일 체결"])
    with tabs[0]:
        _render_candidate_controls(market)
    with tabs[1]:
        if not positions:
            st.info("보유종목이 없습니다.")
        for row in positions:
            if st.button(f"{row.get('name') or row.get('ticker')} · {row.get('ticker')} · {int(row.get('quantity') or 0)}주 · {float(row.get('pnl_rate') or 0):+.2f}%", key=f"holding_{row.get('ticker')}", use_container_width=True):
                st.session_state.ade_order_ticker = str(row.get("ticker"))
                _reset_order_confirmation()
                st.rerun()
    with tabs[2]:
        _render_pending_orders()
    with tabs[3]:
        _render_daily_orders()
    if account:
        st.caption(f"KIS 주문가능 현금 ₩{float(account.get('cash') or 0):,.0f}")
    if error:
        st.caption(error)


def _render_candidate_controls(market: str) -> None:
    query = st.text_input("종목 검색", placeholder="국내 종목코드 6자리")
    normalized_query = _normalize_kr_ticker(query) if market == "kr" else query.strip().upper()
    if query and not normalized_query:
        st.caption("국내 주문은 6자리 숫자 종목코드를 입력하세요.")
    if normalized_query and st.button("주문후보에 추가", type="primary"):
        try:
            _add_order_candidate(market, normalized_query, normalized_query)
            st.rerun()
        except OrderCandidateStoreError as exc:
            st.error(str(exc))
    try:
        legacy_rows = list_legacy_candidates(market)
    except OrderCandidateStoreError as exc:
        st.error(str(exc))
        legacy_rows = []
    if legacy_rows and st.button(f"기존 JSON 후보 {len(legacy_rows)}개 가져오기", key=f"import_legacy_{market}"):
        try:
            imported = import_legacy_candidates(_owner_id(), market)
            st.session_state.ade_order_flash = {"level": "success", "message": f"기존 주문후보 {imported}개를 가져왔습니다."}
            st.rerun()
        except OrderCandidateStoreError as exc:
            st.error(str(exc))
    try:
        rows = _load_order_candidates(market)
    except OrderCandidateStoreError as exc:
        st.error(str(exc))
        rows = []
    if rows:
        if st.session_state.ade_candidate_clear_market == market:
            st.warning(f"{market.upper()} 시장 주문후보 {len(rows)}개를 모두 삭제합니다.")
            c1, c2 = st.columns(2)
            if c1.button("전체 삭제 확정", key=f"confirm_clear_candidates_{market}", type="primary", use_container_width=True):
                clear_candidates(_owner_id(), market)
                st.session_state.ade_candidate_clear_market = None
                st.rerun()
            if c2.button("취소", key=f"cancel_clear_candidates_{market}", use_container_width=True):
                st.session_state.ade_candidate_clear_market = None
                st.rerun()
        elif st.button("현재 시장 후보 전체 삭제", key=f"clear_candidates_{market}"):
            st.session_state.ade_candidate_clear_market = market
            st.rerun()
    for row in rows:
        c1, c2 = st.columns([5, 1])
        ticker = str(row["ticker"])
        target = (market, ticker)
        if c1.button(f"{row['symbol']} · {ticker}", key=f"candidate_{market}_{ticker}", use_container_width=True):
            mark_selected(_owner_id(), market, ticker)
            st.session_state.ade_order_ticker = ticker
            _reset_order_confirmation()
            st.rerun()
        if st.session_state.ade_candidate_delete_target == target:
            if c2.button("확정", key=f"confirm_delete_candidate_{market}_{ticker}", type="primary", use_container_width=True):
                delete_candidate(_owner_id(), market, ticker)
                st.session_state.ade_candidate_delete_target = None
                st.rerun()
        elif c2.button("삭제", key=f"delete_candidate_{market}_{ticker}", use_container_width=True):
            st.session_state.ade_candidate_delete_target = target
            st.rerun()


def _action_is_recent(signature: tuple[Any, ...]) -> bool:
    return (
        st.session_state.ade_last_order_action_signature == signature
        and time.time() - float(st.session_state.ade_last_order_action_at or 0) < ORDER_ACTION_DUPLICATE_WINDOW_SECONDS
    )


def _render_pending_orders() -> None:
    refresh = st.button("미체결 새로고침", key="pending_refresh")
    rows, error = load_pending_orders(refresh=refresh)
    if error:
        st.warning(error)
        return
    if not rows:
        st.info("미체결 주문이 없습니다.")
        return
    for row in rows:
        order_id = str(row.get("order_id") or "")
        with st.container(border=True):
            st.markdown(f"**{row.get('name') or row.get('ticker')}** · 주문번호 `{order_id}` · {row.get('side')} · 잔량 {row.get('remaining_quantity')}주")
            c1, c2, c3 = st.columns([1, 1, 1])
            new_price = c1.number_input("정정가격", min_value=0.0, value=float(row.get("order_price") or 0), step=100.0, key=f"rvp_{order_id}")
            new_qty = c2.number_input("정정수량", min_value=1, max_value=max(1, int(row.get("remaining_quantity") or 1)), value=max(1, int(row.get("remaining_quantity") or 1)), step=1, key=f"rvq_{order_id}")
            organization_no = str(row.get("organization_no") or "")
            revise_signature = ("revise", order_id, int(new_qty), int(new_price))
            revise_disabled = st.session_state.ade_order_action_state == "submitting" or _action_is_recent(revise_signature)
            if c3.button("정정", key=f"rev_{order_id}", use_container_width=True, disabled=revise_disabled):
                correlation_id = uuid.uuid4().hex[:8]
                st.session_state.ade_order_action_state = "submitting"
                try:
                    revise_paper_order(order_id, int(new_qty), float(new_price), organization_no=organization_no)
                    refresh_order_views()
                    st.session_state.ade_last_order_action_signature = revise_signature
                    st.session_state.ade_last_order_action_at = time.time()
                    st.session_state.ade_order_flash = {"level": "success", "message": f"정정 요청 완료 · 요청ID {correlation_id}"}
                except Exception:
                    LOGGER.exception("KIS revise failed correlation_id=%s", correlation_id)
                    st.session_state.ade_order_flash = {"level": "error", "message": f"정정 요청에 실패했습니다. 요청ID {correlation_id}"}
                finally:
                    st.session_state.ade_order_action_state = "idle"
                st.rerun()
            cancel_signature = ("cancel", order_id, int(row.get("remaining_quantity") or 0))
            cancel_disabled = st.session_state.ade_order_action_state == "submitting" or _action_is_recent(cancel_signature)
            if st.button("전체 취소", key=f"can_{order_id}", use_container_width=True, disabled=cancel_disabled):
                correlation_id = uuid.uuid4().hex[:8]
                st.session_state.ade_order_action_state = "submitting"
                try:
                    cancel_paper_order(order_id, int(row.get("remaining_quantity") or 0), organization_no=organization_no)
                    refresh_order_views()
                    st.session_state.ade_last_order_action_signature = cancel_signature
                    st.session_state.ade_last_order_action_at = time.time()
                    st.session_state.ade_order_flash = {"level": "success", "message": f"취소 요청 완료 · 요청ID {correlation_id}"}
                except Exception:
                    LOGGER.exception("KIS cancel failed correlation_id=%s", correlation_id)
                    st.session_state.ade_order_flash = {"level": "error", "message": f"취소 요청에 실패했습니다. 요청ID {correlation_id}"}
                finally:
                    st.session_state.ade_order_action_state = "idle"
                st.rerun()


def _render_daily_orders() -> None:
    refresh = st.button("체결내역 새로고침", key="daily_refresh")
    rows, error = load_daily_orders(executed_only=True, refresh=refresh)
    if error:
        st.warning(error)
        return
    if not rows:
        st.info("당일 체결 내역이 없습니다.")
        return
    shown = []
    for r in rows:
        shown.append({"주문번호": r.get("order_id"), "종목": r.get("name") or r.get("ticker"), "구분": r.get("side"), "주문수량": r.get("order_quantity"), "체결수량": r.get("executed_quantity"), "체결가": r.get("executed_price"), "주문시각": r.get("order_time")})
    st.dataframe(pd.DataFrame(shown), hide_index=True, use_container_width=True)


def _live_state_key(ticker: str, field: str) -> str:
    return f"ade_live_{field}_{ticker}"


def _order_price_key(ticker: str, side: str, order_type: str) -> str:
    return f"ade_order_price_{ticker}_{side}_{order_type}"


def _order_quantity_key(ticker: str, side: str, order_type: str) -> str:
    return f"ade_order_quantity_{ticker}_{side}_{order_type}"


def _reset_order_confirmation() -> None:
    st.session_state.ade_order_confirmation = False
    st.session_state.ade_order_signature = None
    for key in [key for key in st.session_state.keys() if str(key).startswith("ade_order_confirm_")]:
        st.session_state.pop(key, None)


def _render_order_flash() -> None:
    flash = st.session_state.pop("ade_order_flash", None)
    if not flash:
        return
    message = str(flash.get("message") or "")
    if flash.get("level") == "success":
        st.success(message)
    elif flash.get("level") == "warning":
        st.warning(message)
    else:
        st.error(message)


def _touch_live_ticker(ticker: str) -> None:
    lru = [item for item in st.session_state.get("ade_live_ticker_lru", []) if item != ticker]
    lru.append(ticker)
    while len(lru) > LIVE_SESSION_TICKER_LIMIT:
        expired = lru.pop(0)
        _clear_live_ticker_state(expired)
    st.session_state.ade_live_ticker_lru = lru


def _clear_live_ticker_state(ticker: str) -> None:
    for field in ("best_ask", "best_bid", "midpoint", "received_at"):
        st.session_state.pop(_live_state_key(ticker, field), None)


def _clear_live_session_state() -> None:
    for ticker in list(st.session_state.get("ade_live_ticker_lru", [])):
        _clear_live_ticker_state(ticker)
    st.session_state.ade_live_ticker_lru = []


def _acquire_live_lease(ticker: str) -> None:
    previous = st.session_state.get("ade_live_subscription_ticker")
    if previous == ticker:
        return
    client = shared_market_client()
    if previous:
        try:
            client.release(_owner_id(), str(previous))
        except ValueError:
            pass
    client.acquire(_owner_id(), ticker)
    st.session_state.ade_live_subscription_ticker = ticker


def _release_live_lease() -> None:
    ticker = st.session_state.get("ade_live_subscription_ticker")
    if not ticker:
        return
    try:
        shared_market_client().release(_owner_id(), str(ticker))
    except ValueError:
        pass
    st.session_state.ade_live_subscription_ticker = None


def _store_live_prices(ticker: str, best_ask: float, best_bid: float, midpoint: float, received_at: float | None) -> None:
    _touch_live_ticker(ticker)
    st.session_state[_live_state_key(ticker, "best_ask")] = float(best_ask or 0)
    st.session_state[_live_state_key(ticker, "best_bid")] = float(best_bid or 0)
    st.session_state[_live_state_key(ticker, "midpoint")] = float(midpoint or 0)
    st.session_state[_live_state_key(ticker, "received_at")] = received_at


def _load_live_prices(ticker: str, fallback_price: float) -> tuple[float, float, float]:
    received_at = st.session_state.get(_live_state_key(ticker, "received_at"))
    if not received_at or time.time() - float(received_at) > LIVE_PRICE_MAX_AGE_SECONDS:
        _clear_live_ticker_state(ticker)
        return fallback_price, fallback_price, fallback_price
    best_ask = float(st.session_state.get(_live_state_key(ticker, "best_ask"), 0) or fallback_price)
    best_bid = float(st.session_state.get(_live_state_key(ticker, "best_bid"), 0) or fallback_price)
    midpoint = float(st.session_state.get(_live_state_key(ticker, "midpoint"), 0) or fallback_price)
    return best_ask, best_bid, midpoint


def _render_live_orderbook(ticker: str, fallback_price: float) -> tuple[float, float, float, float | None]:
    client = shared_market_client()
    snapshot = client.latest_orderbook(ticker)
    trade = client.latest_trade(ticker)
    received_times = [item.received_at for item in (snapshot, trade) if item is not None]
    latest_received = max(received_times) if received_times else None
    if snapshot is None:
        health = client.health_snapshot()
        st.info("KIS 실시간 호가 연결 중입니다" + (" · 연결 상태를 확인하세요" if health.get("last_error") else ""))
        best_ask, best_bid, midpoint = _load_live_prices(ticker, fallback_price)
        return best_ask, best_bid, midpoint, latest_received
    valid_asks = [level for level in snapshot.asks if level.price > 0 and level.quantity >= 0]
    valid_bids = [level for level in snapshot.bids if level.price > 0 and level.quantity >= 0]
    rows: list[str] = []
    for level in reversed(valid_asks):
        rows.extend(['<div class="ask">매도</div>', f'<div class="mid">{level.price:,.0f}</div>', f'<div>{level.quantity:,}</div>'])
    rows.extend(['<div class="head">구분</div>', '<div class="head">가격</div>', '<div class="head">잔량</div>'])
    for level in valid_bids:
        rows.extend(['<div class="bid">매수</div>', f'<div class="mid">{level.price:,.0f}</div>', f'<div>{level.quantity:,}</div>'])
    st.markdown('<div class="ade-orderbook">' + ''.join(rows) + '</div>', unsafe_allow_html=True)
    best_ask = valid_asks[0].price if valid_asks else fallback_price
    best_bid = valid_bids[0].price if valid_bids else fallback_price
    midpoint = (best_ask + best_bid) / 2 if best_ask and best_bid else fallback_price
    _store_live_prices(ticker, best_ask, best_bid, midpoint, latest_received)
    age = time.time() - snapshot.received_at
    freshness = "정상" if age <= 3 else ("지연" if age <= 10 else "오래됨")
    st.caption(f"매도총잔량 {snapshot.total_ask_quantity:,} · 매수총잔량 {snapshot.total_bid_quantity:,} · 수신 {time.strftime('%H:%M:%S', time.localtime(snapshot.received_at))} · {freshness}")
    return best_ask, best_bid, midpoint, latest_received


def _render_live_market_fragment(ticker: str, fallback_price: float) -> None:
    fragment = getattr(st, "fragment", None)
    if fragment is None:
        _render_live_orderbook(ticker, fallback_price)
        return
    @fragment(run_every=f"{LIVE_REFRESH_SECONDS}s")
    def _fragment_body() -> None:
        _render_live_orderbook(ticker, fallback_price)
        trade = shared_market_client().latest_trade(ticker)
        if trade:
            st.caption(f"최근 체결 {trade.trade_time} · 체결량 {trade.volume:,}주 · 수신 {time.strftime('%H:%M:%S', time.localtime(trade.received_at))}")
    _fragment_body()


def _preflight_order(*, ticker: str, side: str, quantity: int, order_type: str, price: float, holding: dict[str, Any] | None) -> tuple[bool, str, int]:
    if not kis_paper_enabled():
        return False, "실계좌 주문은 차단되어 있습니다. KIS 모의투자 설정을 확인하세요.", 0
    if not _normalize_kr_ticker(ticker):
        return False, "국내 종목코드가 유효하지 않습니다.", 0
    if quantity <= 0:
        return False, "주문수량은 1주 이상이어야 합니다.", 0
    if order_type == "LIMIT" and price <= 0:
        return False, "지정가 주문가격은 0보다 커야 합니다.", 0
    if side == "매수":
        latest, error = load_orderable(ticker, price, order_type, refresh=True)
        if error:
            return False, "최신 주문가능수량 확인에 실패했습니다.", 0
        latest_available = int((latest or {}).get("orderable_quantity") or 0)
    else:
        _, positions, error = _kis_data(True)
        if error and not positions:
            return False, "최신 보유수량 확인에 실패했습니다.", 0
        latest_holding = next((p for p in positions if str(p.get("ticker")) == ticker), holding)
        latest_available = int((latest_holding or {}).get("quantity") or 0)
    if quantity > latest_available:
        return False, f"최신 주문가능수량은 {latest_available:,}주입니다.", latest_available
    return True, "", latest_available


def _render_order_ticket(market: str, ticker: str) -> None:
    if st.button("← 주문목록으로 돌아가기"):
        _release_live_lease()
        st.session_state.ade_order_ticker = None
        _reset_order_confirmation()
        st.rerun()
    normalized_ticker = _normalize_kr_ticker(ticker) if market == "kr" else ticker.strip().upper()
    if market == "kr" and not normalized_ticker:
        _release_live_lease()
        st.error("국내 주문은 6자리 숫자 종목코드만 지원합니다.")
        return
    ticker = normalized_ticker or ticker
    account, positions, error = _kis_data(False) if market == "kr" else (None, [], None)
    holding = next((p for p in positions if str(p.get("ticker")) == str(ticker)), None)
    quote, quote_error = load_kis_quote(ticker) if market == "kr" else (None, None)
    market_client = shared_market_client()
    trade = market_client.latest_trade(ticker) if market == "kr" else None
    default_price = float((trade.price if trade else 0) or (quote or {}).get("price") or (holding or {}).get("current_price") or 0)
    st.markdown(f"## {(holding or {}).get('name') or ticker}")
    if quote or trade:
        live_rate = trade.change_rate if trade else float((quote or {}).get("change_rate") or 0)
        live_change = trade.change if trade else float((quote or {}).get("change") or 0)
        cols = st.columns(9)
        values = [("현재가", default_price), ("전일대비", live_change), ("등락률", f"{live_rate:+.2f}%"), ("시가", trade.open if trade else (quote or {}).get("open")), ("고가", trade.high if trade else (quote or {}).get("high")), ("저가", trade.low if trade else (quote or {}).get("low")), ("누적거래량", f"{int(trade.accumulated_volume if trade else (quote or {}).get('volume') or 0):,}"), ("체결강도", f"{float(trade.trade_strength if trade else 0):.2f}"), ("PER / PBR", f"{float((quote or {}).get('per') or 0):.2f} / {float((quote or {}).get('pbr') or 0):.2f}")]
        for col, (label, value) in zip(cols, values):
            col.metric(label, f"{value:,.0f}" if isinstance(value, (int, float)) else str(value))
    left, right = st.columns([1.2, 1])
    with left:
        live = st.toggle("KIS 실시간 10호가·체결", value=st.session_state.ade_live_orderbook, key="ade_live_orderbook_toggle", disabled=market != "kr" or not kis_configured())
        st.session_state.ade_live_orderbook = live
        refresh = st.toggle(f"{LIVE_REFRESH_SECONDS}초 자동 갱신", value=st.session_state.ade_live_refresh, key="ade_live_refresh_toggle", disabled=not live)
        st.session_state.ade_live_refresh = refresh
        if live and market == "kr":
            _acquire_live_lease(ticker)
            if refresh:
                _render_live_market_fragment(ticker, default_price)
            else:
                _render_live_orderbook(ticker, default_price)
                if trade:
                    st.caption(f"최근 체결 {trade.trade_time} · 체결량 {trade.volume:,}주 · 수신 {time.strftime('%H:%M:%S', time.localtime(trade.received_at))}")
        else:
            _release_live_lease()
        best_ask, best_bid, mid = _load_live_prices(ticker, default_price) if live and market == "kr" else (default_price, default_price, default_price)
    with right:
        side = st.radio("주문 구분", ["매수", "매도"], horizontal=True, key=f"ade_order_side_{ticker}")
        order_type_label = st.selectbox("주문유형", ["지정가", "시장가"], key=f"ade_order_type_{ticker}")
        order_type = "LIMIT" if order_type_label == "지정가" else "MARKET"
        context = (ticker, side, order_type)
        if st.session_state.ade_order_context != context:
            st.session_state.ade_order_context = context
            _reset_order_confirmation()
        live_default = best_ask if side == "매수" else best_bid
        if order_type == "LIMIT":
            price_key = _order_price_key(ticker, side, order_type)
            if price_key not in st.session_state:
                st.session_state[price_key] = float(live_default or default_price)
            price = st.number_input("가격", min_value=0.0, step=100.0, key=price_key)
            reference = float(price)
        else:
            price = 0.0
            reference = float(mid or default_price)
            st.metric("예상 기준가", f"₩{reference:,.0f}")
            st.caption("시장가는 실제 체결가가 예상 기준가와 다를 수 있습니다.")
        orderable, orderable_error = load_orderable(ticker, reference, order_type) if side == "매수" and market == "kr" else (None, None)
        max_sell = int((holding or {}).get("quantity") or 0)
        available = int((orderable or {}).get("orderable_quantity") or 0) if side == "매수" else max_sell
        quantity_key = _order_quantity_key(ticker, side, order_type)
        if quantity_key not in st.session_state:
            st.session_state[quantity_key] = 1 if available > 0 else 0
        if available <= 0:
            st.session_state[quantity_key] = 0
        elif int(st.session_state.get(quantity_key, 0)) > available:
            st.session_state[quantity_key] = available
        quantity = st.number_input("수량", min_value=0, max_value=available if available > 0 else 0, step=1, key=quantity_key)
        c1, c2 = st.columns(2)
        c1.metric("주문가능수량", f"{available:,}주")
        c2.metric("예상금액", f"₩{reference * quantity:,.0f}")
        if orderable:
            st.caption(f"KIS 주문가능현금 ₩{float(orderable.get('orderable_cash') or 0):,.0f}")
        signature = (ticker, side, order_type, round(float(price), 4) if order_type == "LIMIT" else None, int(quantity))
        if st.session_state.ade_order_signature is not None and st.session_state.ade_order_signature != signature:
            _reset_order_confirmation()
        st.session_state.ade_order_signature = signature
        confirm_key = f"ade_order_confirm_{ticker}_{side}_{order_type}"
        confirmed = st.checkbox("주문 내용을 확인했습니다.", key=confirm_key)
        st.session_state.ade_order_confirmation = bool(confirmed)
        submitting = st.session_state.ade_order_submit_state == "submitting"
        recent_duplicate = st.session_state.ade_last_submitted_signature == signature and time.time() - float(st.session_state.ade_last_submitted_at or 0) < ORDER_DUPLICATE_WINDOW_SECONDS
        can_submit = market == "kr" and kis_paper_enabled() and quantity > 0 and confirmed and quantity <= available and not submitting and not recent_duplicate
        if recent_duplicate:
            st.caption("동일 주문의 연속 전송을 잠시 차단했습니다.")
        if st.button(f"{side} 주문 전송", type="primary", use_container_width=True, disabled=not can_submit):
            request_id = uuid.uuid4().hex
            st.session_state.ade_order_submit_state = "submitting"
            st.session_state.ade_last_client_request_id = request_id
            try:
                ok, preflight_error, _latest_available = _preflight_order(ticker=ticker, side=side, quantity=int(quantity), order_type=order_type, price=float(reference if order_type == "MARKET" else price), holding=holding)
                if not ok:
                    st.session_state.ade_order_submit_state = "failed"
                    st.session_state.ade_order_flash = {"level": "error", "message": preflight_error}
                    st.rerun()
                result = submit_paper_order(ticker=ticker, side="BUY" if side == "매수" else "SELL", quantity=int(quantity), order_type=order_type, limit_price=float(price) if order_type == "LIMIT" else None)
                if result.accepted:
                    st.session_state.ade_order_submit_state = "accepted"
                    st.session_state.ade_last_submitted_signature = signature
                    st.session_state.ade_last_submitted_at = time.time()
                    st.session_state.ade_order_flash = {"level": "success", "message": f"접수 완료 · 주문번호 {result.order_id or '-'} · 요청ID {request_id[:8]}"}
                    _reset_order_confirmation()
                    refresh_order_views()
                    _kis_data(True)
                    st.rerun()
                st.session_state.ade_order_submit_state = "failed"
                st.session_state.ade_order_flash = {"level": "error", "message": f"주문이 거절되었습니다. 요청ID {request_id[:8]}"}
                st.rerun()
            except Exception:
                LOGGER.exception("KIS submit failed request_id=%s", request_id)
                st.session_state.ade_order_submit_state = "failed"
                st.session_state.ade_order_flash = {"level": "error", "message": f"주문 전송에 실패했습니다. 요청ID {request_id[:8]}"}
                st.rerun()
            finally:
                if st.session_state.ade_order_submit_state == "submitting":
                    st.session_state.ade_order_submit_state = "idle"
        health = market_client.health_snapshot()
        if error or quote_error or orderable_error or health.get("last_error"):
            st.caption("일부 데이터 연결 상태를 확인하세요.")


def _render_jp_radar() -> None:
    st.markdown("## JP Radar")
    market = _market_selector("ade_jp_market")
    ticker = st.text_input("종목코드", value=st.session_state.ade_jp_ticker or ("005930" if market == "kr" else "AAPL"))
    try:
        result = JPStockRadarEngine().analyze(ticker, intraday_period="5d", intraday_interval="5m")
    except Exception:
        correlation_id = uuid.uuid4().hex[:8]
        LOGGER.exception("JP Radar failed correlation_id=%s", correlation_id)
        st.error(f"JP Radar 분석에 실패했습니다. 요청ID {correlation_id}")
        return
    st.plotly_chart(make_live_radar_chart(result, mobile=False, period_days=365), use_container_width=True, config={"displaylogo": False,"scrollZoom": True,"responsive": True})


def _market_selector(key: str) -> str:
    value = st.segmented_control("시장", options=["kr", "us"], default=st.session_state.get("ade_market", "kr"), format_func=lambda v: "국내" if v == "kr" else "미국", key=key, label_visibility="collapsed")
    return str(value or "kr")


def _load_recommendations(market: str):
    profile = get_market_profile(market)
    if not profile.db_path.exists():
        return [], None
    with sqlite3.connect(str(profile.db_path), timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        context = load_latest_context(conn, profile.code, 50)
        if context is None:
            return [], None
        name_map = build_name_map(conn, profile.code)
        rows = []
        for source in context.recommendations:
            row = dict(source)
            ticker = normalize_ticker(row.get("ticker"), market)
            row["ticker"] = ticker
            row["symbol"] = name_map.get(ticker) or row.get("name") or ticker
            rows.append(row)
        return rows, context


def _normalize_kr_ticker(value: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{1,6}", text):
        return ""
    return text.zfill(6)


def _owner_id() -> str:
    return str(st.session_state.ade_owner_id)


def _add_order_candidate(market: str, ticker: str, symbol: str) -> None:
    upsert_candidate(_owner_id(), market, ticker, symbol)


def _load_order_candidates(market: str | None = None) -> list[dict[str, Any]]:
    return list_candidates(_owner_id(), market)


def _render_status_bar() -> None:
    workspace = get_workspace(st.session_state.ade_ui_workspace)
    if kis_paper_enabled():
        kis_text, kis_class = "KIS 모의투자 설정", "ade-ok"
    elif kis_configured():
        kis_text, kis_class = "KIS 설정 확인 필요", ""
    else:
        kis_text, kis_class = "KIS 미설정", ""
    health = shared_market_client().health_snapshot()
    latest_received_at = health.get("latest_received_at")
    if health.get("connected") and latest_received_at:
        age = time.time() - float(latest_received_at)
        ws_text = "실시간 정상" if age <= 3 else ("실시간 지연" if age <= 10 else "실시간 오래됨")
        ws_class = "ade-ok" if age <= 3 else ""
    elif health.get("connected"):
        ws_text, ws_class = "실시간 연결·수신대기", ""
    else:
        ws_text, ws_class = "실시간 대기", ""
    candidate_health = store_health()
    schema_version = candidate_health.get("schema_version")
    candidate_text = f"후보DB 정상 v{schema_version}" if candidate_health.get("status") == "정상" else "후보DB 오류"
    candidate_class = "ade-ok" if candidate_health.get("status") == "정상" else ""
    st.markdown(f'<div class="ade-statusbar"><span>{workspace.short_name}</span><span>AI 데이터 부분 연결</span><span class="ade-ok">DB 정상</span><span class="{kis_class}">{kis_text}</span><span class="{ws_class}">{ws_text}</span><span>Yahoo 참고용</span><span class="{candidate_class}">{candidate_text}</span><span>추천·Replay·STO 규칙 유지</span></div>', unsafe_allow_html=True)


def _safe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}
