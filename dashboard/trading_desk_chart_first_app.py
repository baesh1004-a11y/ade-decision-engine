from __future__ import annotations

import os
import sqlite3
from types import SimpleNamespace

import pandas as pd

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
from markets.symbol_display import display_symbol, normalize_ticker
from meta_score.validation_context import EnvironmentAdvisor
from trading.order_service import TradingOrderService


def _format_price(value: float) -> str:
    return f"{value:,.0f}원"


def _load_market_snapshot(st) -> dict[str, dict[str, object]]:
    @st.cache_data(ttl=300, show_spinner=False)
    def _fetch() -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        try:
            import yfinance as yf
        except ImportError:
            return result

        symbols = {
            "KOSPI": "^KS11",
            "KOSDAQ": "^KQ11",
            "USD/KRW": "KRW=X",
        }
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
        (
            row.get(key)
            for key in ("current_price", "last_price", "close", "price")
            if row.get(key) not in (None, "")
        ),
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


def _load_fallback_bars(db_path: str, ticker: str) -> tuple[pd.DataFrame, str]:
    try:
        import yfinance as yf

        for yahoo_ticker in _yahoo_candidates(ticker):
            try:
                frame = yf.download(
                    yahoo_ticker,
                    period="5d",
                    interval="5m",
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
                normalized = _normalize_yahoo_frame(frame)
                if not normalized.empty:
                    return normalized, f"Yahoo Finance 5분봉 ({yahoo_ticker}) · KIS 조회 실패 시 대체"
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
               ORDER BY trade_date DESC LIMIT 120""",
            (code, f"{code}.KS", f"{code}.KQ"),
        ).fetchall()
        return pd.DataFrame([dict(row) for row in reversed(rows)]), "내부 최신 저장 시세 · KIS 조회 실패 시 대체"
    finally:
        conn.close()


def _load_live_market_data(st, db_path: str, ticker: str) -> tuple[pd.DataFrame, dict[str, object], str, str | None]:
    code = normalize_ticker(ticker, "kr")

    @st.cache_resource(show_spinner=False)
    def _kis_client():
        return kis_market_data_from_env()

    try:
        client = _kis_client()
        bars = client.get_intraday_bars(code, include_previous=True)
        quote = client.get_current_quote(code)
        if not bars.empty:
            return bars, quote, "한국투자증권 KIS 장중 분봉", None
        error = "KIS 분봉 응답이 비어 있습니다."
    except Exception as exc:
        quote = {}
        error = str(exc)

    fallback_bars, fallback_source = _load_fallback_bars(db_path, ticker)
    return fallback_bars, quote, fallback_source, error


def _render_chart_with_quote_panel(st, db_path: str, ticker: str, label: str) -> None:
    st.markdown(f"### 현재 차트 · {label}")
    bars, quote, source, kis_error = _load_live_market_data(st, db_path, ticker)
    if bars.empty:
        st.warning("현재 차트 데이터를 불러오지 못했습니다.")
        if kis_error:
            st.caption(f"KIS 조회 오류: {kis_error}")
        return

    chart_column, quote_column = st.columns([4, 1], gap="medium")
    with chart_column:
        st.plotly_chart(
            build_trading_chart(bars, label),
            use_container_width=True,
            config=CHART_CONFIG,
        )

    latest = bars.iloc[-1]
    current_price = float(quote.get("current_price") or latest["Close"])
    change = float(quote.get("change") or 0.0)
    change_rate = float(quote.get("change_rate") or 0.0)
    high = float(quote.get("high") or latest["High"])
    low = float(quote.get("low") or latest["Low"])
    volume = float(quote.get("volume") or latest.get("Volume") or 0.0)
    ask_price = float(quote.get("ask_price") or 0.0)
    bid_price = float(quote.get("bid_price") or 0.0)

    with quote_column:
        st.markdown("#### 실시간 시세")
        st.metric("현재가", _format_price(current_price), f"{change:+,.0f}원 ({change_rate:+.2f}%)")
        st.metric("고가", _format_price(high))
        st.metric("저가", _format_price(low))
        st.metric("누적 거래량", f"{volume:,.0f}")
        st.markdown("#### 매수·매도 호가")
        if ask_price > 0 or bid_price > 0:
            st.metric("최우선 매도", _format_price(ask_price) if ask_price > 0 else "미제공")
            st.metric("최우선 매수", _format_price(bid_price) if bid_price > 0 else "미제공")
        else:
            st.info("현재가 응답에 호가가 포함되지 않았습니다.")

    st.caption(f"시세 출처: {source} · 차트와 우측 현재가는 같은 KIS 종목 데이터를 우선 사용합니다.")
    if kis_error:
        st.warning(f"KIS 차트 조회 실패로 대체 데이터를 표시했습니다: {kis_error}")


def _render_radar_panel(st, selected: dict, ticker: str) -> None:
    st.markdown("#### JP Radar")
    if st.button("JP Radar 실행", use_container_width=True, key=f"jp_radar_tab_{ticker}"):
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
        st.page_link("pages/2_Meta_Score.py", label="추천 검증 화면 열기", icon="✅", use_container_width=True)
    else:
        st.caption("숫자 점수 대신 저장된 검증 결과와 정성적 환경 수준만 표시합니다.")


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 한국 주문관리", page_icon="💳", layout="wide")

    env = os.getenv("KIS_ENV", "paper").lower()
    live_enabled = os.getenv("KIS_LIVE_ORDER_ENABLED", "NO").upper() == "YES"
    service = TradingOrderService(db_path)

    try:
        recommendations = service.latest_recommendations(50)
        requests = service.pending_requests(100)
        current_run_id = str(recommendations[0]["run_id"]) if recommendations else ""
        pending_count = sum(
            1
            for row in requests
            if row["status"] == "PENDING_APPROVAL"
            and (not current_run_id or str(row.get("source_run_id") or "") == current_run_id)
        )

        _style(st)
        _render_status_header(st, env, live_enabled, len(recommendations), pending_count)
        _render_market_status(st)
        st.markdown("### 1. 추천 Watch List")

        if not recommendations:
            st.warning("최신 완료 추천 결과가 없습니다. 먼저 통합 추천 워크벤치에서 추천을 생성하세요.")
            _render_pending_approval(st, service, recommendations)
            _render_execution_and_history(st, service)
            return

        run_id = str(recommendations[0]["run_id"])
        run_finished = str(recommendations[0].get("run_finished_at") or "-")
        st.caption(
            f"추천 완료: {run_finished} · "
            "왼쪽 종목에 마우스를 올리면 핵심정보가 표시되고, 클릭하면 차트가 전환됩니다."
        )

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
        st.session_state[selection_key] = min(
            max(int(st.session_state[selection_key]), 0),
            len(recommendations) - 1,
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
                    use_container_width=True,
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
            _render_selected_summary(st, selected, selected_label)
            _render_chart_with_quote_panel(st, db_path, str(selected["ticker"]), selected_label)

            radar_tab, validation_tab, order_tab = st.tabs(["JP Radar", "추천 검증", "주문"])
            with radar_tab:
                _render_radar_panel(st, selected, selected_code)
            with validation_tab:
                _render_validation_panel(st, selected)
            with order_tab:
                _render_order_form(st, service, selected, selected_code, selected_label, run_id)

        st.divider()
        _render_pending_approval(st, service, recommendations)
        _render_execution_and_history(st, service)
    finally:
        service.close()
