from __future__ import annotations

import os
import sqlite3
from types import SimpleNamespace

import pandas as pd
import streamlit as st

from broker.kis_market_data import kis_market_data_from_env
from dashboard.trading_desk_app import (
    _decision_label,
    _render_execution_and_history,
    _render_order_form,
    _render_pending_approval,
    _render_selected_summary,
    _render_status_header,
    _style,
    _watch_label,
)
from dashboard.charts import CHART_CONFIG, build_trading_chart
from dashboard.trading_desk_ui import render_empty_state, render_mobile_bottom_nav, render_view_mode
from markets.symbol_display import display_symbol, normalize_ticker
from meta_score.validation_context import EnvironmentAdvisor
from trading.order_service import TradingOrderService


ELIGIBLE_DECISIONS = {"FINAL BUY", "BUY WATCH"}


@st.cache_resource(show_spinner=False)
def _cached_kis_client():
    return kis_market_data_from_env()


@st.cache_data(ttl=5, max_entries=200, show_spinner=False)
def _cached_kis_quote(ticker: str) -> dict[str, object]:
    return _cached_kis_client().get_current_quote(ticker)


@st.cache_data(ttl=900, max_entries=100, show_spinner=False)
def _cached_kis_daily_bars(ticker: str) -> pd.DataFrame:
    return _cached_kis_client().get_daily_bars(ticker, lookback_days=365)


@st.cache_data(ttl=30, max_entries=100, show_spinner=False)
def _cached_kis_intraday_bars(ticker: str) -> pd.DataFrame:
    return _cached_kis_client().get_intraday_bars(ticker, include_previous=True)


@st.cache_data(ttl=30, max_entries=100, show_spinner=False)
def _cached_kis_four_hour_bars(ticker: str) -> pd.DataFrame:
    return _cached_kis_client().get_four_hour_bars(ticker)


def _clear_market_data_cache() -> None:
    _cached_kis_quote.clear()
    _cached_kis_daily_bars.clear()
    _cached_kis_intraday_bars.clear()
    _cached_kis_four_hour_bars.clear()


def _format_price(value: float) -> str:
    return f"{value:,.0f}원"


def _is_mobile_request(st) -> bool:
    """Best-effort mobile detection without adding a front-end dependency."""
    try:
        user_agent = str(st.context.headers.get("User-Agent", "")).lower()
    except Exception:
        return False
    return any(token in user_agent for token in ("android", "iphone", "ipad", "ipod", "mobile"))


def _render_mobile_status_header(
    st, env: str, live_enabled: bool, recommendation_count: int, pending_count: int
) -> None:
    if env == "live" and live_enabled:
        mode_label = "실전주문 활성"
        mode_class = "danger"
    elif env == "live":
        mode_label = "실전환경 · 주문 잠금"
        mode_class = "warning"
    else:
        mode_label = "모의투자"
        mode_class = "safe"

    st.markdown(
        f"""
        <div class="mobile-status-bar">
          <div class="mobile-status-title">한국 주문관리</div>
          <div class="mobile-status-items">
            <span class="status-badge {mode_class}">● {mode_label}</span>
            <span class="status-badge neutral">추천 {recommendation_count}</span>
            <span class="status-badge neutral">승인대기 {pending_count}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("주문 진행 방식 보기"):
        st.caption("추천 → 차트 확인 → 판단 도구 → 주문 요청 → 사용자 승인 → KIS 전송")


def _load_market_snapshot(st) -> dict[str, dict[str, object]]:
    @st.cache_data(ttl=300, show_spinner=False)
    def _fetch() -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        try:
            import yfinance as yf
        except ImportError:
            return result

        symbols = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "USD/KRW": "KRW=X"}
        for label, symbol in symbols.items():
            try:
                history = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)
                closes = history["Close"].dropna()
                if closes.empty:
                    continue
                current = float(closes.iloc[-1])
                previous = float(closes.iloc[-2]) if len(closes) > 1 else current
                change_rate = ((current - previous) / previous * 100.0) if previous else 0.0
                result[label] = {"value": current, "change_rate": change_rate}
            except Exception:
                continue
        return result

    return _fetch()


def _render_market_status(st) -> None:
    snapshot = _load_market_snapshot(st)
    st.markdown("### 오늘의 시장 현황")
    st.caption("지수와 환율의 조회값만 표시합니다. 전망·매매 판단·시장 해석은 포함하지 않습니다.")

    cards = st.columns(6, gap="small")
    items = [
        ("KOSPI", "KOSPI"),
        ("KOSDAQ", "KOSDAQ"),
        ("USD/KRW", "USD/KRW"),
        ("거래대금", None),
        ("외국인", None),
        ("기관", None),
    ]
    for column, (title, snapshot_key) in zip(cards, items):
        with column:
            data = snapshot.get(snapshot_key) if snapshot_key else None
            if data is None:
                st.metric(title, "미연동")
                continue
            value = float(data["value"])
            change_rate = float(data["change_rate"])
            value_text = f"{value:,.2f}" if title != "USD/KRW" else f"{value:,.1f}원"
            st.metric(title, value_text, f"{change_rate:+.2f}%")

    st.caption("조회: Yahoo Finance · 5분 캐시 · 수급 및 거래대금은 검증된 데이터 연결 전까지 표시하지 않습니다.")


def _watch_hover_text(st, row: dict, ticker: str) -> str:
    decision = _decision_label(str(row.get("decision") or "UNVALIDATED"))
    weekly = float(row.get("weekly_similarity") or 0.0)
    sto = float(row.get("sto_similarity") or 0.0)
    current_price = next(
        (row.get(key) for key in ("current_price", "last_price", "close", "price") if row.get(key) not in (None, "")),
        None,
    )
    try:
        price_text = _format_price(float(current_price)) if current_price is not None else "차트 선택 후 확인"
    except (TypeError, ValueError):
        price_text = "차트 선택 후 확인"

    radar = st.session_state.get(f"jp_radar_result_{ticker}")
    if radar is None:
        radar_text = "미실행"
    else:
        market_signal = str(getattr(radar, "market_signal", "-") or "-")
        sector_signal = str(getattr(radar, "sector_signal", "-") or "-")
        radar_text = f"시장 {market_signal} / 업종 {sector_signal}"

    return (
        f"현재가: {price_text}\n"
        f"추천 등급: {decision}\n"
        f"주봉 유사도: {weekly:.1f}%\n"
        f"STO 유사도: {sto:.1f}%\n"
        f"JP Radar: {radar_text}"
    )


def _normalize_yahoo_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.reset_index()
    date_column = "Datetime" if "Datetime" in frame.columns else "Date"
    frame = frame.rename(columns={date_column: "Date"})
    keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"] if c in frame.columns]
    return frame[keep].dropna(subset=["Close"])


def _yahoo_candidates(ticker: str) -> list[str]:
    raw = str(ticker).strip().upper()
    code = normalize_ticker(raw, "kr")
    if raw.endswith(".KQ"):
        return [f"{code}.KQ"]
    if raw.endswith(".KS"):
        return [f"{code}.KS"]
    return [f"{code}.KS", f"{code}.KQ"]


@st.cache_data(ttl=60, max_entries=200, show_spinner=False)
def _load_fallback_bars(db_path: str, ticker: str, timeframe: str) -> tuple[pd.DataFrame, str]:
    period, interval = ("1y", "1d") if timeframe == "일봉" else ("5d", "5m")
    try:
        import yfinance as yf

        for yahoo_ticker in _yahoo_candidates(ticker):
            try:
                frame = yf.download(
                    yahoo_ticker,
                    period=period,
                    interval=interval,
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
                normalized = _normalize_yahoo_frame(frame)
                if normalized.empty:
                    continue
                if timeframe == "4시간봉":
                    normalized = (
                        normalized.set_index("Date")
                        .resample("4h", origin="start_day", offset="9h")
                        .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
                        .dropna(subset=["Open", "Close"])
                        .reset_index()
                    )
                return normalized, f"Yahoo Finance {timeframe} · KIS 조회 실패 시 대체"
            except Exception:
                continue
    except ImportError:
        pass

    code = normalize_ticker(ticker, "kr")
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT trade_date AS Date, open AS Open, high AS High, low AS Low,
                      close AS Close, volume AS Volume
               FROM price_bars
               WHERE market='kr' AND ticker IN (?, ?, ?)
               ORDER BY trade_date DESC LIMIT 240""",
            (code, f"{code}.KS", f"{code}.KQ"),
        ).fetchall()
        return pd.DataFrame([dict(row) for row in reversed(rows)]), "내부 최신 저장 일봉 · KIS 조회 실패 시 대체"
    finally:
        conn.close()


def _load_live_market_data(
    st, db_path: str, ticker: str, timeframe: str
) -> tuple[pd.DataFrame, dict[str, object], str, str | None]:
    code = normalize_ticker(ticker, "kr")

    errors: list[str] = []
    try:
        quote = _cached_kis_quote(code)
    except Exception as exc:
        quote = {}
        errors.append(f"현재가: {exc}")

    try:
        if timeframe == "일봉":
            bars = _cached_kis_daily_bars(code)
            source = "한국투자증권 KIS 일봉"
        elif timeframe == "4시간봉":
            bars = _cached_kis_four_hour_bars(code)
            source = "한국투자증권 KIS 4시간봉"
        else:
            bars = _cached_kis_intraday_bars(code)
            source = "한국투자증권 KIS 장중 분봉"
        if not bars.empty:
            return bars, quote, source, " / ".join(errors) or None
        errors.append(f"KIS {timeframe} 응답이 비어 있습니다.")
    except Exception as exc:
        errors.append(f"차트: {exc}")

    fallback_bars, fallback_source = _load_fallback_bars(db_path, ticker, timeframe)
    return fallback_bars, quote, fallback_source, " / ".join(errors) or None


def _render_chart_with_quote_panel(st, db_path: str, ticker: str, label: str, mobile: bool = False) -> None:
    if mobile:
        st.markdown(f"### 현재 차트 · {label}")
        timeframe = st.selectbox(
            "차트 주기",
            ["일봉", "4시간봉", "장중 분봉"],
            index=0,
            key=f"chart_timeframe_{normalize_ticker(ticker, 'kr')}",
        )
        if st.button("시세 새로고침", key=f"refresh_market_{normalize_ticker(ticker, 'kr')}"):
            _clear_market_data_cache()
            _load_fallback_bars.clear()
            st.rerun()
    else:
        title_col, control_col, refresh_col = st.columns([4, 1, 1])
        with title_col:
            st.markdown(f"### 현재 차트 · {label}")
        with control_col:
            timeframe = st.selectbox(
                "차트 주기",
                ["일봉", "4시간봉", "장중 분봉"],
                index=0,
                key=f"chart_timeframe_{normalize_ticker(ticker, 'kr')}",
                label_visibility="collapsed",
            )
        with refresh_col:
            if st.button("시세 새로고침", key=f"refresh_market_{normalize_ticker(ticker, 'kr')}"):
                _clear_market_data_cache()
                _load_fallback_bars.clear()
                st.rerun()

    bars, quote, source, kis_error = _load_live_market_data(st, db_path, ticker, timeframe)
    if bars.empty:
        render_empty_state(
            st, "한국 차트를 불러오지 못했습니다",
            "KIS 연결과 종목코드를 확인한 뒤 시세 새로고침을 실행하세요.", icon=":material/error:",
        )
        if kis_error:
            st.caption(f"KIS 조회 오류: {kis_error}")
        return

    latest = bars.iloc[-1]
    live_quote = quote.get("current_price") not in (None, "", 0, 0.0)
    current_price = float(quote.get("current_price") or latest["Close"])
    change = float(quote.get("change") or 0.0) if live_quote else None
    change_rate = float(quote.get("change_rate") or 0.0) if live_quote else None
    high = float(quote.get("high") or latest["High"])
    low = float(quote.get("low") or latest["Low"])
    volume = float(quote.get("volume") or latest.get("Volume") or 0.0)
    ask_price = float(quote.get("ask_price") or 0.0)
    bid_price = float(quote.get("bid_price") or 0.0)

    if mobile:
        st.plotly_chart(build_trading_chart(bars, label), width="stretch", config=CHART_CONFIG)
        quote_cols = st.columns(2)
        quote_cols[0].metric(
            "현재가" if live_quote else "최근 확인 가격",
            _format_price(current_price),
            f"{change:+,.0f}원 ({change_rate:+.2f}%)" if live_quote else None,
        )
        quote_cols[1].metric("누적 거래량", f"{volume:,.0f}")
        quote_cols = st.columns(2)
        quote_cols[0].metric("고가", _format_price(high))
        quote_cols[1].metric("저가", _format_price(low))
        with st.expander("매수·매도 호가"):
            if ask_price > 0 or bid_price > 0:
                bid_ask = st.columns(2)
                bid_ask[0].metric("최우선 매도", _format_price(ask_price) if ask_price > 0 else "미제공")
                bid_ask[1].metric("최우선 매수", _format_price(bid_price) if bid_price > 0 else "미제공")
            else:
                st.info("현재가 응답에 호가가 포함되지 않았습니다.")
    else:
        chart_column, quote_column = st.columns([4, 1], gap="medium")
        with chart_column:
            st.plotly_chart(build_trading_chart(bars, label), width="stretch", config=CHART_CONFIG)
        with quote_column:
            st.markdown("#### 실시간 시세" if live_quote else "#### 최근 확인 가격")
            st.metric(
                "현재가" if live_quote else "대체 데이터 종가",
                _format_price(current_price),
                f"{change:+,.0f}원 ({change_rate:+.2f}%)" if live_quote else None,
            )
            st.metric("고가", _format_price(high))
            st.metric("저가", _format_price(low))
            st.metric("누적 거래량", f"{volume:,.0f}")
            st.markdown("#### 매수·매도 호가")
            if ask_price > 0 or bid_price > 0:
                st.metric("최우선 매도", _format_price(ask_price) if ask_price > 0 else "미제공")
                st.metric("최우선 매수", _format_price(bid_price) if bid_price > 0 else "미제공")
            else:
                st.info("현재가 응답에 호가가 포함되지 않았습니다.")

    captured_at = quote.get("captured_at") if live_quote else latest.get("Date", "-")
    freshness = "KIS 실시간 현재가" if live_quote else "대체 데이터 · 실시간 아님"
    st.caption(f"시세 출처: {source} · {freshness} · 기준 시각 {captured_at or '-'}")
    if timeframe == "4시간봉" and len(bars) < 10:
        st.info("KIS 장중 분봉 제공 범위가 짧아 4시간봉 표본이 적을 수 있습니다. 중기 판단은 일봉을 권장합니다.")
    if kis_error:
        st.warning(f"KIS 차트 조회 실패로 대체 데이터를 표시했습니다: {kis_error}")


def _render_radar_panel(st, selected: dict, ticker: str) -> None:
    st.markdown("#### JP Radar")
    if st.button("JP Radar 실행", width="stretch", key=f"jp_radar_tab_{ticker}"):
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
    if radar is None:
        st.info("JP Radar를 실행하면 전체 시장과 해당 업종의 환경 신호를 표시합니다.")
        return

    a, b = st.columns(2)
    a.metric("전체 시장", str(getattr(radar, "market_signal", "-") or "-"))
    b.metric("해당 업종", str(getattr(radar, "sector_signal", "-") or "-"))


def _environment_label(value) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "미확인"
    if score >= 70:
        return "양호"
    if score >= 45:
        return "중립"
    return "주의"


def _risk_level(value) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "미확인"
    if score >= 70:
        return "높음"
    if score >= 45:
        return "보통"
    return "낮음"


def _render_validation_panel(st, selected: dict) -> None:
    decision = str(selected.get("decision") or "UNVALIDATED")
    st.markdown("#### 추천 검증")
    st.metric("검증 결과", _decision_label(decision))
    cols = st.columns(3)
    cols[0].metric("전체 시장 환경", _environment_label(selected.get("market_score")))
    cols[1].metric("해당 업종 환경", _environment_label(selected.get("sector_score")))
    cols[2].metric("종목 위험", _risk_level(selected.get("risk_score")))

    if decision == "UNVALIDATED":
        st.info("아직 저장된 검증 결과가 없습니다. 통합 추천 워크벤치에서 환경 검증을 실행하세요.")
        st.page_link("pages/2_Meta_Score.py", label="추천 검증 화면 열기", icon="✅", width="stretch")
    else:
        st.caption("숫자 점수 대신 저장된 검증 결과와 정성적 환경 수준만 표시합니다.")


def _render_mobile_order_form(st, service, selected: dict, ticker: str, label: str, run_id: str) -> None:
    st.markdown("### 일반 주문")
    decision = str(selected.get("decision") or "UNVALIDATED")
    validated = bool(selected.get("validation_available"))
    eligible = decision in ELIGIBLE_DECISIONS

    st.markdown(f"**선택 종목:** {label}")
    side_labels = {"매수": "BUY", "매도": "SELL"}
    order_type_labels = {"시장가": "MARKET", "지정가": "LIMIT"}

    side_label = st.radio(
        "주문 방향",
        list(side_labels),
        horizontal=True,
        key=f"mobile_side_label_{ticker}",
    )
    quantity = st.number_input(
        "수량",
        min_value=1,
        value=1,
        step=1,
        key=f"mobile_quantity_{ticker}",
    )
    order_type_label = st.radio(
        "주문 방식",
        list(order_type_labels),
        horizontal=True,
        key=f"mobile_order_type_label_{ticker}",
    )

    side = side_labels[side_label]
    order_type = order_type_labels[order_type_label]
    limit_price = 0.0
    if order_type == "LIMIT":
        limit_price = st.number_input(
            "지정가",
            min_value=0.0,
            value=0.0,
            step=10.0,
            key=f"mobile_limit_price_{ticker}",
        )

    with st.expander("상세 설정 · 익절/손절"):
        target = st.number_input(
            "익절 기준 수익률(%)",
            value=float(selected.get("target_return") or 0.0),
            step=0.1,
            key=f"mobile_target_{ticker}",
        )
        stop = st.number_input(
            "손절 기준 수익률(%)",
            value=float(selected.get("stop_return") or 0.0),
            step=0.1,
            key=f"mobile_stop_{ticker}",
        )

    price_phrase = "시장가로" if order_type == "MARKET" else f"{float(limit_price):,.0f}원 지정가로"
    summary = f"{label} {int(quantity)}주를 {price_phrase} {side_label}합니다."
    risk_summary = f"목표 수익률 {float(target):+.1f}% · 손절 기준 {float(stop):+.1f}%"
    st.markdown(
        f"""
        <div class="order-summary">
          <div class="order-summary-label">주문 요약</div>
          <div class="order-summary-main">{summary}</div>
          <div class="order-summary-risk">{risk_summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not validated:
        st.caption("미검증 종목도 주문 리스트와 주문 입력은 유지됩니다. 매수 요청 전 검증 조언 확인을 권장합니다.")
    elif not eligible and side == "BUY":
        st.warning(f"현재 검증 조언은 {_decision_label(decision)}입니다. 주문 전 사용자가 직접 판단해야 합니다.")

    invalid_limit = order_type == "LIMIT" and float(limit_price) <= 0
    if invalid_limit:
        st.warning("지정가 주문은 0원보다 큰 가격을 입력해야 합니다.")

    if st.button(
        "주문 요청 만들기",
        type="primary",
        width="stretch",
        key=f"mobile_create_order_{ticker}",
        disabled=invalid_limit,
    ):
        request_id = service.create_request(
            ticker=ticker,
            name=selected.get("name"),
            side=side,
            quantity=int(quantity),
            order_type=order_type,
            limit_price=None if order_type == "MARKET" else float(limit_price),
            target_return=float(target),
            stop_return=float(stop),
            source_run_id=run_id,
            source_rank=int(selected["rank_no"]),
        )
        st.success(f"주문 요청 생성: {request_id}. 아직 KIS로 전송되지 않았습니다.")


def _inject_mobile_styles(st) -> None:
    st.markdown(
        """
        <style>
        .mobile-status-bar {
            padding: 0.15rem 0 0.55rem 0;
            border-bottom: 1px solid rgba(120, 130, 150, 0.22);
            margin-bottom: 0.25rem;
        }
        .mobile-status-title {
            font-size: 1.45rem;
            font-weight: 750;
            margin-bottom: 0.45rem;
        }
        .mobile-status-items {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
        }
        @media (max-width: 768px) {
            .block-container {padding-top: 0.75rem; padding-left: 0.85rem; padding-right: 0.85rem;}
            div[data-testid="stMetric"] {padding: 0.45rem 0.2rem;}
            div[data-testid="stPlotlyChart"] {margin-top: -0.3rem;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 한국 주문관리", page_icon="💳", layout="wide")
    env = os.getenv("KIS_ENV", "paper").lower()
    live_enabled = os.getenv("KIS_LIVE_ORDER_ENABLED", "NO").upper() == "YES"
    service = TradingOrderService(db_path)
    mobile = _is_mobile_request(st)

    try:
        recommendations = service.latest_recommendations(50)
        requests = service.pending_approval_requests()
        current_run_id = str(recommendations[0]["run_id"]) if recommendations else ""
        pending_count = len(requests)

        _style(st)
        _inject_mobile_styles(st)
        if mobile:
            _render_mobile_status_header(st, env, live_enabled, len(recommendations), pending_count)
        else:
            _render_status_header(st, env, live_enabled, len(recommendations), pending_count)
        view_mode = render_view_mode(st, service, market="kr")
        mobile_section = "차트"
        if mobile:
            mobile_section = str(st.session_state.get("kr_mobile_section", "차트"))
            render_mobile_bottom_nav(st, pending_count=pending_count, state_key="kr_mobile_section")
        elif view_mode == "상세 보기":
            _render_market_status(st)

        st.markdown("### 1. 추천 Watch List")
        if not recommendations:
            render_empty_state(
                st, "추천 결과가 없습니다",
                "통합 추천 워크벤치에서 추천을 생성한 뒤 다시 확인하세요.",
                icon=":material/playlist_add:",
            )
            _render_pending_approval(st, service, recommendations)
            _render_execution_and_history(st, service)
            return

        run_id = str(recommendations[0]["run_id"])
        run_finished = str(recommendations[0].get("run_finished_at") or "-")
        labels = [_watch_label(row) for row in recommendations]
        selected_from_workbench = normalize_ticker(st.session_state.get("workbench_selected_kr") or "", "kr")
        default_index = next(
            (
                i
                for i, row in enumerate(recommendations)
                if normalize_ticker(row["ticker"], "kr") == selected_from_workbench
            ),
            0,
        )
        selection_key = "trading_order_selected_kr_chart_first_index"
        if selection_key not in st.session_state:
            st.session_state[selection_key] = default_index
        st.session_state[selection_key] = min(max(int(st.session_state[selection_key]), 0), len(recommendations) - 1)

        if mobile:
            index = st.selectbox(
                "종목 선택",
                range(len(recommendations)),
                index=int(st.session_state[selection_key]),
                format_func=lambda i: labels[i].replace("\n", " · "),
                key="mobile_trading_order_selector",
            )
            st.session_state[selection_key] = int(index)
            st.caption(f"추천 완료: {run_finished} · 총 {len(recommendations)}개 추천 종목")

            selected = recommendations[int(index)]
            selected_code = normalize_ticker(selected["ticker"], "kr")
            selected_label = display_symbol(selected.get("name"), selected_code, "kr")
            st.session_state["workbench_selected_kr"] = selected_code

            if mobile_section == "추천":
                _render_selected_summary(st, selected, selected_label)
            elif mobile_section == "차트":
                _render_chart_with_quote_panel(st, db_path, str(selected["ticker"]), selected_label, mobile=True)
                _render_selected_summary(st, selected, selected_label)
            elif mobile_section == "분석":
                _render_radar_panel(st, selected, selected_code)
                if view_mode == "상세 보기":
                    _render_validation_panel(st, selected)
            elif mobile_section == "주문":
                _render_order_form(st, service, selected, selected_code, selected_label, run_id)

            if view_mode == "상세 보기" and mobile_section in ("추천", "분석"):
                with st.expander("오늘의 시장 현황", icon=":material/public:"):
                    _render_market_status(st)
        else:
            st.caption(
                f"추천 완료: {run_finished} · "
                "왼쪽 종목에 마우스를 올리면 핵심정보가 표시되고, 클릭하면 차트가 전환됩니다."
            )
            watch_column, detail_column = st.columns([1, 3], gap="large")
            with watch_column:
                st.markdown("#### 추천 종목")
                for i, row in enumerate(recommendations):
                    ticker = normalize_ticker(row["ticker"], "kr")
                    if st.button(
                        labels[i],
                        key=f"watch_hover_{ticker}_{i}",
                        help=_watch_hover_text(st, row, ticker),
                        type="primary" if i == st.session_state[selection_key] else "secondary",
                        width="stretch",
                    ):
                        st.session_state[selection_key] = i
                st.caption("종목 버튼에 마우스를 올리면 상세정보를 볼 수 있습니다.")
                st.caption("● 매수 검토  ● 관찰  ● 보류  ● 제외  ● 미검증")
                st.caption(f"총 {len(recommendations)}개 추천 종목")

            index = int(st.session_state[selection_key])
            selected = recommendations[index]
            selected_code = normalize_ticker(selected["ticker"], "kr")
            selected_label = display_symbol(selected.get("name"), selected_code, "kr")
            st.session_state["workbench_selected_kr"] = selected_code

            with detail_column:
                with st.container(border=True):
                    _render_selected_summary(st, selected, selected_label)
                    _render_chart_with_quote_panel(st, db_path, str(selected["ticker"]), selected_label)

                detail_view = st.segmented_control(
                    "상세 화면", ["JP Radar", "추천 검증", "주문"], default="JP Radar",
                    key=f"desktop_detail_view_{selected_code}", label_visibility="collapsed",
                )
                if detail_view == "JP Radar":
                    _render_radar_panel(st, selected, selected_code)
                elif detail_view == "추천 검증" and view_mode == "상세 보기":
                    _render_validation_panel(st, selected)
                else:
                    _render_order_form(st, service, selected, selected_code, selected_label, run_id)

        if not mobile or mobile_section == "승인":
            _render_pending_approval(st, service, recommendations)
        if not mobile and view_mode == "상세 보기":
            _render_execution_and_history(st, service)
    finally:
        service.close()
