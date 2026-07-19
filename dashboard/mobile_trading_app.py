from __future__ import annotations

import os
from types import SimpleNamespace

import pandas as pd
import streamlit as st

from broker.kis_market_data import kis_market_data_from_env
from dashboard.charts import CHART_CONFIG, build_trading_chart
from dashboard.trading_desk_app import (
    _decision_label,
    _render_execution_and_history,
    _render_pending_approval,
    _watch_label,
)
from dashboard.trading_desk_chart_first_app import (
    _environment_label,
    _load_fallback_bars,
    _load_market_snapshot,
    _risk_level,
)
from markets.symbol_display import display_symbol, normalize_ticker
from meta_score.validation_context import EnvironmentAdvisor
from trading.order_service import TradingOrderService


ELIGIBLE_DECISIONS = {"FINAL BUY", "BUY WATCH"}


def _fmt_price(value: float) -> str:
    return f"{value:,.0f}원"


def _load_market_data(db_path: str, ticker: str, timeframe: str):
    code = normalize_ticker(ticker, "kr")
    try:
        client = kis_market_data_from_env()
        quote = client.get_current_quote(code)
        if timeframe == "일봉":
            bars = client.get_daily_bars(code, lookback_days=365)
            source = "한국투자증권 KIS 일봉"
        elif timeframe == "4시간봉":
            bars = client.get_four_hour_bars(code)
            source = "한국투자증권 KIS 4시간봉"
        else:
            bars = client.get_intraday_bars(code, include_previous=True)
            source = "한국투자증권 KIS 장중 분봉"
        if not bars.empty:
            return bars, quote, source, None
        error = f"KIS {timeframe} 응답이 비어 있습니다."
    except Exception as exc:
        quote = {}
        error = str(exc)

    bars, source = _load_fallback_bars(db_path, ticker, timeframe)
    return bars, quote, source, error


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {background: #f4f7fb;}
        .block-container {
            max-width: 560px;
            padding-top: .65rem;
            padding-left: .8rem;
            padding-right: .8rem;
            padding-bottom: 6.5rem;
        }
        header[data-testid="stHeader"] {background: transparent;}
        [data-testid="stSidebar"] {display: none;}
        .mobile-top {
            display:flex; justify-content:space-between; align-items:center;
            margin: .1rem 0 .65rem 0;
        }
        .brand {font-size:1.42rem; font-weight:800; color:#102a56; letter-spacing:-.02em;}
        .mode-pill {
            border:1px solid #d7e1ef; background:#fff; border-radius:999px;
            padding:.38rem .65rem; font-size:.82rem; font-weight:700; color:#3b516f;
        }
        .market-strip {
            display:grid; grid-template-columns:repeat(3,1fr); gap:.4rem;
            background:#fff; border:1px solid #e3eaf3; border-radius:14px;
            padding:.7rem .45rem; box-shadow:0 4px 18px rgba(35,61,98,.06);
            margin-bottom:.85rem;
        }
        .market-cell {text-align:center; min-width:0;}
        .market-label {font-size:.72rem; font-weight:800; color:#223a5f;}
        .market-value {font-size:.76rem; color:#586d88; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
        .market-up {font-size:.72rem; color:#ef4d55; font-weight:700;}
        .market-down {font-size:.72rem; color:#1769e0; font-weight:700;}
        .hero-card {
            background:#fff; border:1px solid #e1e8f2; border-radius:18px;
            padding:1rem; margin:.8rem 0 .75rem 0;
            box-shadow:0 8px 24px rgba(31,64,106,.07);
        }
        .hero-head {display:flex; align-items:center; gap:.5rem; flex-wrap:wrap;}
        .hero-name {font-size:1.2rem; font-weight:850; color:#132d54;}
        .decision-pill {
            display:inline-block; border-radius:999px; padding:.28rem .55rem;
            background:#fff0de; color:#e47a00; font-size:.76rem; font-weight:850;
        }
        .hero-sub {font-size:.82rem; color:#71839a; margin-top:.18rem;}
        .hero-main {display:grid; grid-template-columns:1.35fr .65fr .65fr; gap:.55rem; align-items:end; margin-top:.75rem;}
        .hero-price {font-size:2rem; font-weight:900; color:#f1464f; letter-spacing:-.04em;}
        .hero-change {font-size:.86rem; color:#f1464f; font-weight:750;}
        .score-box {border:1px solid #dfe7f1; border-radius:13px; padding:.65rem .4rem; text-align:center; background:#fbfdff;}
        .score-label {font-size:.72rem; color:#6b7f99;}
        .score-value {font-size:1.28rem; font-weight:850; color:#1769e0;}
        .score-value.green {color:#13a36f;}
        .mini-grid {display:grid; grid-template-columns:repeat(4,1fr); gap:.35rem; margin-top:.5rem;}
        .mini-card {background:#fff; border:1px solid #e3eaf3; border-radius:12px; padding:.62rem .3rem; text-align:center;}
        .mini-label {font-size:.68rem; color:#70849b;}
        .mini-value {font-size:.84rem; font-weight:800; color:#1b355a; margin-top:.12rem;}
        .section-card {background:#fff; border:1px solid #e1e8f2; border-radius:16px; padding:.8rem; box-shadow:0 6px 18px rgba(31,64,106,.05);}
        div[data-testid="stPlotlyChart"] {margin-top:-.4rem;}
        div[data-testid="stMetric"] {background:#fff; border:1px solid #e2e8f1; border-radius:12px; padding:.45rem .5rem;}
        div[role="radiogroup"] {gap:.28rem;}
        div[role="radiogroup"] label {background:#fff; border:1px solid #dce5f0; border-radius:10px; padding:.38rem .48rem;}
        button[kind="primary"] {border-radius:12px; min-height:3rem; font-weight:800;}
        .nav-title {font-size:.78rem; color:#6e8299; margin:.4rem 0 .2rem; text-align:center;}
        @media (max-width: 420px) {
            .hero-main {grid-template-columns:1fr 1fr;}
            .hero-main > div:first-child {grid-column:1 / -1;}
            .hero-price {font-size:1.8rem;}
            .mini-grid {grid-template-columns:repeat(2,1fr);}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_top(env: str, live_enabled: bool, pending_count: int) -> None:
    mode = "실전주문" if env == "live" and live_enabled else "모의투자"
    st.markdown(
        f"""
        <div class="mobile-top">
          <div class="brand">ADE Trading</div>
          <div class="mode-pill">● {mode} · 승인 {pending_count}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_market_strip() -> None:
    snapshot = _load_market_snapshot(st)
    cells = []
    for key in ("KOSPI", "KOSDAQ", "USD/KRW"):
        data = snapshot.get(key)
        if data:
            value = float(data["value"])
            rate = float(data["change_rate"])
            value_text = f"{value:,.2f}" if key != "USD/KRW" else f"{value:,.1f}"
            cls = "market-up" if rate >= 0 else "market-down"
            cells.append(
                f'<div class="market-cell"><div class="market-label">{key}</div>'
                f'<div class="market-value">{value_text}</div><div class="{cls}">{rate:+.2f}%</div></div>'
            )
        else:
            cells.append(
                f'<div class="market-cell"><div class="market-label">{key}</div>'
                '<div class="market-value">미연동</div><div class="market-value">-</div></div>'
            )
    st.markdown(f'<div class="market-strip">{"".join(cells)}</div>', unsafe_allow_html=True)


def _render_hero(selected: dict, label: str, quote: dict, bars: pd.DataFrame) -> None:
    latest = bars.iloc[-1]
    current = float(quote.get("current_price") or latest["Close"])
    change = float(quote.get("change") or 0.0)
    rate = float(quote.get("change_rate") or 0.0)
    decision = _decision_label(str(selected.get("decision") or "UNVALIDATED"))
    weekly = float(selected.get("weekly_similarity") or 0.0)
    sto = float(selected.get("sto_similarity") or 0.0)
    ticker = normalize_ticker(selected["ticker"], "kr")
    sector = str(selected.get("sector") or "업종 미분류")
    sign = "▲" if change >= 0 else "▼"
    color = "#f1464f" if change >= 0 else "#1769e0"
    st.markdown(
        f"""
        <div class="hero-card">
          <div class="hero-head"><span class="hero-name">{label}</span><span class="decision-pill">{decision}</span></div>
          <div class="hero-sub">{ticker} | {sector}</div>
          <div class="hero-main">
            <div>
              <div class="hero-price" style="color:{color}">{current:,.0f}원</div>
              <div class="hero-change" style="color:{color}">{sign} {abs(change):,.0f}원 &nbsp; {rate:+.2f}%</div>
            </div>
            <div class="score-box"><div class="score-label">주봉 적합도</div><div class="score-value">{weekly:.0f}%</div></div>
            <div class="score-box"><div class="score-label">STO 적합도</div><div class="score-value green">{sto:.0f}%</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_chart_screen(db_path: str, selected: dict, label: str) -> None:
    ticker = str(selected["ticker"])
    timeframe = st.radio("차트 주기", ["일봉", "4시간봉", "장중 분봉"], horizontal=True, key=f"mobile_tf_{ticker}")
    bars, quote, source, error = _load_market_data(db_path, ticker, timeframe)
    if bars.empty:
        st.warning("차트 데이터를 불러오지 못했습니다.")
        if error:
            st.caption(error)
        return
    _render_hero(selected, label, quote, bars)
    st.plotly_chart(build_trading_chart(bars, label), use_container_width=True, config=CHART_CONFIG)
    latest = bars.iloc[-1]
    high = float(quote.get("high") or latest["High"])
    low = float(quote.get("low") or latest["Low"])
    volume = float(quote.get("volume") or latest.get("Volume") or 0.0)
    ask = float(quote.get("ask_price") or 0.0)
    bid = float(quote.get("bid_price") or 0.0)
    st.markdown(
        f"""
        <div class="mini-grid">
          <div class="mini-card"><div class="mini-label">오늘 고가</div><div class="mini-value">{high:,.0f}</div></div>
          <div class="mini-card"><div class="mini-label">오늘 저가</div><div class="mini-value">{low:,.0f}</div></div>
          <div class="mini-card"><div class="mini-label">거래량</div><div class="mini-value">{volume:,.0f}</div></div>
          <div class="mini-card"><div class="mini-label">매도 / 매수</div><div class="mini-value">{ask:,.0f} / {bid:,.0f}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"시세 출처: {source}")
    if error:
        st.warning(f"KIS 조회 실패로 대체 데이터를 표시했습니다: {error}")


def _render_judgment_screen(selected: dict, ticker: str) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### AI 종합 판단")
    decision = _decision_label(str(selected.get("decision") or "UNVALIDATED"))
    st.metric("현재 판단", decision)
    cols = st.columns(3)
    cols[0].metric("시장", _environment_label(selected.get("market_score")))
    cols[1].metric("업종", _environment_label(selected.get("sector_score")))
    cols[2].metric("위험", _risk_level(selected.get("risk_score")))
    st.markdown("#### JP Radar")
    if st.button("JP Radar 실행", type="primary", use_container_width=True, key=f"mobile_radar_{ticker}"):
        recommendation = SimpleNamespace(
            market="kr",
            ticker=ticker,
            name=selected.get("name"),
            prediction=None,
            matched_max_drawdown=float(selected.get("matched_max_drawdown") or 0.0),
        )
        st.session_state[f"jp_radar_result_{ticker}"] = EnvironmentAdvisor().analyze(recommendation)
        st.rerun()
    radar = st.session_state.get(f"jp_radar_result_{ticker}")
    if radar is not None:
        a, b = st.columns(2)
        a.metric("전체 시장", str(getattr(radar, "market_signal", "-") or "-"))
        b.metric("해당 업종", str(getattr(radar, "sector_signal", "-") or "-"))
    else:
        st.info("JP Radar를 실행하면 시장 및 업종 환경을 확인할 수 있습니다.")
    st.markdown("</div>", unsafe_allow_html=True)


def _render_order_screen(service: TradingOrderService, selected: dict, ticker: str, label: str, run_id: str) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### 주문")
    side_label = st.radio("주문 방향", ["매수", "매도"], horizontal=True, key=f"m_side_{ticker}")
    quantity = st.number_input("수량", min_value=1, value=1, step=1, key=f"m_qty_{ticker}")
    order_type_label = st.radio("주문 방식", ["시장가", "지정가"], horizontal=True, key=f"m_type_{ticker}")
    order_type = "MARKET" if order_type_label == "시장가" else "LIMIT"
    limit_price = None
    if order_type == "LIMIT":
        limit_price = st.number_input("지정가", min_value=0.0, value=0.0, step=10.0, key=f"m_limit_{ticker}")
    with st.expander("상세 설정 · 익절/손절"):
        target = st.number_input("익절 기준(%)", value=float(selected.get("target_return") or 0.0), step=0.1, key=f"m_target_{ticker}")
        stop = st.number_input("손절 기준(%)", value=float(selected.get("stop_return") or 0.0), step=0.1, key=f"m_stop_{ticker}")
    price_text = "시장가" if order_type == "MARKET" else f"{float(limit_price or 0):,.0f}원"
    st.info(f"{label} {int(quantity)}주 · {price_text} · {side_label}")
    disabled = order_type == "LIMIT" and float(limit_price or 0) <= 0
    if st.button("주문 요청 만들기", type="primary", use_container_width=True, disabled=disabled, key=f"m_create_{ticker}"):
        request_id = service.create_request(
            ticker=ticker,
            name=selected.get("name"),
            side="BUY" if side_label == "매수" else "SELL",
            quantity=int(quantity),
            order_type=order_type,
            limit_price=None if order_type == "MARKET" else float(limit_price),
            target_return=float(target),
            stop_return=float(stop),
            source_run_id=run_id,
            source_rank=int(selected["rank_no"]),
        )
        st.success(f"주문 요청 생성: {request_id}")
    st.markdown("</div>", unsafe_allow_html=True)


def run(db_path: str = "datahub/market.db") -> None:
    st.set_page_config(page_title="ADE Mobile Trading", page_icon="📱", layout="centered", initial_sidebar_state="collapsed")
    _inject_styles()
    env = os.getenv("KIS_ENV", "paper").lower()
    live_enabled = os.getenv("KIS_LIVE_ORDER_ENABLED", "NO").upper() == "YES"
    service = TradingOrderService(db_path)
    try:
        recommendations = service.latest_recommendations(50)
        requests = service.pending_requests(100)
        pending_count = sum(1 for row in requests if row["status"] == "PENDING_APPROVAL")
        _render_top(env, live_enabled, pending_count)
        _render_market_strip()
        if not recommendations:
            st.warning("최신 완료 추천 결과가 없습니다.")
            return

        labels = [_watch_label(row).replace("\n", " · ") for row in recommendations]
        index = st.selectbox(
            "종목 선택",
            range(len(recommendations)),
            format_func=lambda i: labels[i],
            key="mobile_dedicated_selector",
        )
        selected = recommendations[int(index)]
        ticker = normalize_ticker(selected["ticker"], "kr")
        label = display_symbol(selected.get("name"), ticker, "kr")
        run_id = str(selected["run_id"])
        st.session_state["workbench_selected_kr"] = ticker

        st.markdown('<div class="nav-title">핵심 기능</div>', unsafe_allow_html=True)
        screen = st.radio(
            "화면",
            ["📈 차트", "🎯 판단", "🛒 주문", "📋 승인"],
            horizontal=True,
            label_visibility="collapsed",
            key="mobile_bottom_nav",
        )

        if screen == "📈 차트":
            _render_chart_screen(db_path, selected, label)
        elif screen == "🎯 판단":
            _render_judgment_screen(selected, ticker)
        elif screen == "🛒 주문":
            _render_order_screen(service, selected, ticker, label, run_id)
        else:
            _render_pending_approval(st, service, recommendations)
            _render_execution_and_history(st, service)
    finally:
        service.close()
