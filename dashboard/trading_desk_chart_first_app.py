from __future__ import annotations

import os

from dashboard.trading_desk_app import (
    _ai_confidence,
    _decision_label,
    _load_live_bars,
    _render_ai_confidence_card,
    _render_analysis_actions,
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
                result[label] = {
                    "value": current,
                    "change_rate": change_rate,
                }
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
    radar = st.session_state.get(f"jp_radar_result_{ticker}")
    score, level, _, _, _ = _ai_confidence(row, radar)
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

    if radar is None:
        radar_text = "미실행"
    else:
        market_signal = str(getattr(radar, "market_signal", "-") or "-")
        sector_signal = str(getattr(radar, "sector_signal", "-") or "-")
        radar_text = f"시장 {market_signal} / 업종 {sector_signal}"

    return (
        f"현재가: {price_text}\n"
        f"AI 신뢰도: {score}점 ({level})\n"
        f"추천 등급: {decision}\n"
        f"주봉 유사도: {weekly:.1f}%\n"
        f"STO 유사도: {sto:.1f}%\n"
        f"JP Radar: {radar_text}"
    )


def _render_chart_with_quote_panel(st, db_path: str, ticker: str, label: str) -> None:
    st.markdown(f"### 현재 차트 · {label}")
    bars, source = _load_live_bars(db_path, ticker)
    if bars.empty:
        st.warning("현재 차트 데이터를 불러오지 못했습니다.")
        return

    chart_column, quote_column = st.columns([4, 1], gap="medium")
    with chart_column:
        st.plotly_chart(
            build_trading_chart(bars, label),
            use_container_width=True,
            config=CHART_CONFIG,
        )

    latest = bars.iloc[-1]
    previous_close = float(bars.iloc[-2]["Close"]) if len(bars) > 1 else float(latest["Close"])
    current_price = float(latest["Close"])
    change = current_price - previous_close
    change_rate = (change / previous_close * 100.0) if previous_close else 0.0

    with quote_column:
        st.markdown("#### 실시간 시세")
        st.metric("현재가", _format_price(current_price), f"{change:+,.0f}원 ({change_rate:+.2f}%)")
        st.metric("고가", _format_price(float(latest["High"])))
        st.metric("저가", _format_price(float(latest["Low"])))
        st.metric("거래량", f"{float(latest.get('Volume') or 0):,.0f}")
        st.markdown("#### 매수·매도 호가")
        st.info("실시간 호가 API 미연동")
        st.caption("호가 데이터가 연결되면 이 영역에 최우선 매도·매수호가를 표시합니다.")

    st.caption(f"시세 출처: {source} · 종목을 변경하거나 새로고침하면 최신 데이터를 다시 조회합니다.")


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
            _render_chart_with_quote_panel(st, db_path, selected_code, selected_label)

            ai_tab, radar_tab, validation_tab, order_tab = st.tabs(
                ["AI 신뢰도", "JP Radar", "추천 검증", "주문"]
            )
            with ai_tab:
                _render_ai_confidence_card(st, selected, selected_code)
            with radar_tab:
                _render_analysis_actions(st, selected, selected_code)
            with validation_tab:
                st.session_state[f"validation_open_{selected_code}"] = True
                _render_analysis_actions(st, selected, selected_code)
            with order_tab:
                _render_order_form(st, service, selected, selected_code, selected_label, run_id)

        st.divider()
        _render_pending_approval(st, service, recommendations)
        _render_execution_and_history(st, service)
    finally:
        service.close()
