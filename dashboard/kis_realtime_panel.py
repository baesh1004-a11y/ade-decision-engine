from __future__ import annotations

import pandas as pd

from broker.kis_realtime import KISRealtimeClient, RealtimeSnapshot
from dashboard.charts import CHART_CONFIG, build_trading_chart
from markets.symbol_display import normalize_ticker


def render_kis_realtime_panel() -> None:
    """Render a user-triggered KIS realtime snapshot for the selected KR ticker."""
    import streamlit as st

    ticker = normalize_ticker(st.session_state.get("workbench_selected_kr") or "", "kr")
    st.markdown("### KIS 실시간 체결가·호가 스냅샷")
    if not ticker:
        st.caption("위 주문 리스트에서 종목을 먼저 선택하세요.")
        return

    seconds = st.slider("실시간 수집 시간(초)", 2, 15, 5, key=f"kis_rt_seconds_{ticker}")
    c1, c2 = st.columns([3, 1])
    c1.caption(
        "KIS WebSocket에서 국내주식 체결가와 10단계 호가를 동시에 구독해 지정 시간 동안 수집합니다. "
        "실전 주문 활성화와는 무관한 시세 조회 기능입니다."
    )
    collect = c2.button("KIS 실시간 연결", type="primary", use_container_width=True, key=f"kis_rt_collect_{ticker}")

    cache_key = f"kis_rt_snapshot_{ticker}"
    if collect:
        try:
            with st.spinner(f"{ticker} 실시간 시세를 {seconds}초 동안 수집하고 있습니다..."):
                st.session_state[cache_key] = KISRealtimeClient().collect(ticker, seconds=float(seconds))
        except Exception as exc:
            st.error(f"KIS 실시간 연결 실패: {exc}")
            st.info(
                "KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT, KIS_PRODUCT_CODE, KIS_ENV 설정과 "
                "Open API 서비스 신청 상태를 확인하세요."
            )
            return

    snapshot = st.session_state.get(cache_key)
    if snapshot is None:
        st.caption("버튼을 누르면 선택 종목의 실제 KIS 실시간 데이터가 표시됩니다.")
        return
    _render_snapshot(st, snapshot)


def _render_snapshot(st, snapshot: RealtimeSnapshot) -> None:
    trades = pd.DataFrame(snapshot.trades)
    last_trade = snapshot.trades[-1] if snapshot.trades else None
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("소켓", "열림" if snapshot.socket_opened else "실패")
    m2.metric("체결 구독", "정상" if snapshot.trade_subscribed else "미확인")
    m3.metric("호가 구독", "정상" if snapshot.orderbook_subscribed else "미확인")
    m4.metric("현재가", f"{float(last_trade['Close']):,.0f}" if last_trade else "미수신")
    m5.metric("등락률", f"{float(last_trade['change_rate']):.2f}%" if last_trade else "미수신")

    if not snapshot.connected:
        st.warning("WebSocket은 열렸지만 체결가 또는 호가 구독 성공을 확인하지 못했습니다. 연결 메시지를 확인하세요.")

    candles = snapshot.candles("1min")
    if len(candles) >= 2:
        st.plotly_chart(
            build_trading_chart(candles, f"{snapshot.ticker} · KIS 실시간 1분봉"),
            use_container_width=True,
            config=CHART_CONFIG,
        )
    elif not trades.empty:
        line = trades[["Date", "Close"]].copy()
        line["Date"] = pd.to_datetime(line["Date"], errors="coerce")
        st.line_chart(line.dropna().set_index("Date"), use_container_width=True)
        st.caption("수집 시간이 짧아 완성된 1분봉이 부족하므로 체결가 선으로 표시합니다.")
    else:
        st.warning("수집 시간 동안 체결 데이터가 들어오지 않았습니다. 장 운영시간과 구독 상태를 확인하세요.")

    if snapshot.orderbook:
        st.markdown("#### 실시간 10단계 호가")
        st.dataframe(_orderbook_frame(snapshot.orderbook), use_container_width=True, hide_index=True)
    else:
        st.caption("호가 데이터가 수신되지 않았습니다.")

    if snapshot.messages:
        with st.expander("KIS 연결 메시지", expanded=not snapshot.connected):
            for message in snapshot.messages[-20:]:
                st.write(message)
    st.caption(
        f"마지막 수집: {snapshot.captured_at or '-'} · 지정 시간 수집 후 연결을 닫는 스냅샷 방식입니다."
    )


def _orderbook_frame(orderbook: dict) -> pd.DataFrame:
    rows = []
    asks = orderbook.get("asks") or []
    bids = orderbook.get("bids") or []
    ask_qty = orderbook.get("ask_qty") or []
    bid_qty = orderbook.get("bid_qty") or []
    levels = min(10, len(asks), len(bids), len(ask_qty), len(bid_qty))
    for index in range(levels - 1, -1, -1):
        rows.append({"구분": f"매도 {index + 1}", "가격": asks[index], "잔량": ask_qty[index]})
    for index in range(levels):
        rows.append({"구분": f"매수 {index + 1}", "가격": bids[index], "잔량": bid_qty[index]})
    return pd.DataFrame(rows)
