from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.economic_calendar_service import load_economic_calendar
from dashboard.market_overview_service import load_market_overview, load_sector_strength
from markets.profiles import get_market_profile


_STICKY_KPI_STYLE = """
<style>
/* Situation board market strip: keep the six market KPIs visible while scrolling. */
.ade-market-sticky-anchor + div[data-testid="stHorizontalBlock"]{
    position: sticky;
    top: 3.35rem;
    z-index: 930;
    padding: .45rem 0 .6rem;
    background: rgba(247,251,255,.92);
    backdrop-filter: blur(18px) saturate(1.2);
    border-bottom: 1px solid rgba(91,122,153,.18);
}
</style>
"""


def _number(row: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        try:
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _render_market_kpis(refresh: bool) -> None:
    metrics, warning = load_market_overview(refresh=refresh)
    ordered = ["kospi", "kosdaq", "sp500", "nasdaq", "usdkrw", "vix"]
    st.markdown('<div class="ade-market-sticky-anchor"></div>', unsafe_allow_html=True)
    columns = st.columns(6)
    for column, key in zip(columns, ordered):
        metric = metrics.get(key)
        if metric is None or metric.value is None:
            column.metric(metric.label if metric else key.upper(), "조회 실패")
            continue
        delta = f"{metric.change_rate:+.2f}%" if metric.change_rate is not None else None
        column.metric(metric.label, f"{metric.value:,.2f}", delta)
    if warning:
        st.caption(warning)


def _event_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    preferred = ["일시(KST)", "국가", "구분", "이벤트", "중요도", "출처", "비고"]
    return frame[[column for column in preferred if column in frame.columns]]


def _render_market_context(refresh: bool) -> None:
    st.markdown("### 주요 이벤트")
    rows, warning = load_economic_calendar(days_ahead=90, refresh=refresh)
    important = [row for row in rows if str(row.get("중요도") or "") in {"높음", "매우 높음"}]
    if important:
        st.dataframe(_event_frame(important[:5]), hide_index=True, use_container_width=True)
    else:
        st.info("표시할 주요 이벤트가 없습니다.")
    if warning:
        st.caption(warning)
    with st.expander("향후 90일 전체 일정", expanded=False):
        if rows:
            st.dataframe(_event_frame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("표시할 전체 이벤트가 없습니다.")

    st.markdown("### 국내 업종 등락 순위")
    sectors, sector_warning = load_sector_strength(get_market_profile("kr").db_path, limit=10, refresh=refresh)
    if sectors:
        frame = pd.DataFrame(sectors)
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
        st.info("국내 업종 등락 데이터를 아직 가져오지 못했습니다.")
    if sector_warning:
        st.caption(sector_warning)


def _render_position_detail(base_app: Any, row: dict[str, Any]) -> None:
    ticker = _text(row, "ticker", "symbol", "code")
    name = _text(row, "name", "symbol_name", "stock_name") or ticker
    quantity = int(_number(row, "quantity", "qty", "holding_quantity"))
    avg_price = _number(row, "average_price", "avg_price", "purchase_price", "buy_price")
    current_price = _number(row, "current_price", "price", "last_price")
    evaluation = _number(row, "evaluation_amount", "evaluation", "market_value")
    pnl = _number(row, "pnl", "profit_loss", "evaluation_profit_loss")
    invested = avg_price * quantity if avg_price > 0 and quantity > 0 else max(0.0, evaluation - pnl)
    pnl_rate = pnl / invested * 100 if invested > 0 else _number(row, "pnl_rate", "profit_rate", "return_rate")

    if st.button("← 상황종합판으로", key="portfolio_detail_back"):
        st.session_state.ade_portfolio_ticker = None
        st.rerun()

    st.markdown(f"## {name} · {ticker}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("보유수량", f"{quantity:,}주")
    c2.metric("평균매입가", f"₩{avg_price:,.0f}" if avg_price else "-")
    c3.metric("현재가", f"₩{current_price:,.0f}" if current_price else "-")
    c4.metric("평가손익", f"₩{pnl:+,.0f}", f"{pnl_rate:+.2f}%")
    c5.metric("평가금액", f"₩{evaluation:,.0f}" if evaluation else "-")

    st.markdown("### 보유 포지션 차트")
    profile = base_app.get_market_profile("kr")
    normalized = base_app.normalize_ticker(ticker, "kr")
    with base_app.sqlite3.connect(str(profile.db_path), timeout=5) as conn:
        conn.row_factory = base_app.sqlite3.Row
        current, source, warning = base_app._load_current_bars_resilient(conn, "kr", normalized, profile.price_source)
    if current.empty:
        st.info("표시할 가격 이력이 없습니다.")
    else:
        try:
            chart = base_app.build_trading_chart(current, f"{name} · {ticker}", height=680)
            if avg_price > 0:
                chart.add_hline(y=avg_price, line_dash="dash", annotation_text=f"내 평균매입가 {avg_price:,.0f}", row=1, col=1)
            st.plotly_chart(chart, use_container_width=True, config=base_app.CHART_CONFIG, key=f"portfolio_chart_{ticker}")
        except Exception as exc:
            st.caption(f"차트 표시 실패: {exc}")
    st.caption(f"가격소스 {source}")
    if warning:
        st.caption(warning)

    st.markdown("### 수급")
    supply = base_app.load_supply_demand_health(normalized, market="kr")
    investor = supply.get("investor") if isinstance(supply, dict) else None
    if isinstance(investor, dict):
        st.info(str(investor.get("detail") or "수급 세부정보가 없습니다."))
    else:
        st.info("수급 세부정보가 없습니다.")

    st.markdown("### ADE 분석")
    recommendations, context = base_app._load_recommendations("kr")
    recommendation = next((item for item in recommendations if str(item.get("ticker")) == str(ticker)), None)
    if recommendation:
        payload = base_app._safe_json(recommendation.get("payload_json"))
        score = _number(recommendation, "score", "final_similarity", "weekly_similarity")
        sto = _number(recommendation, "sto_similarity")
        replay = payload.get("replay_matches") if isinstance(payload, dict) else []
        k1, k2, k3 = st.columns(3)
        k1.metric("현재 추천점수", f"{score:.1f}")
        k2.metric("STO 유사도", f"{sto:.1f}%")
        k3.metric("Replay", f"{len(replay) if isinstance(replay, list) else 0}건")
        if context is not None:
            st.caption(f"추천 실행ID {context.run_id}")
        if st.button("추천 검증 데스크 열기", key=f"portfolio_reco_{ticker}", use_container_width=True):
            st.session_state.ade_recommendation_detail = ticker
            st.session_state.ade_primary_page = "추천결과"
            st.rerun()
    else:
        st.info("현재 저장된 추천결과에는 이 보유종목이 없습니다. 추천 없음은 매도 신호를 의미하지 않습니다.")

    st.markdown("### 뉴스·공시")
    news_rows, news_warning = base_app._cached_security_news(ticker, name, 8)
    if news_rows:
        st.dataframe(news_rows, hide_index=True, use_container_width=True)
    else:
        st.info("표시할 최신 뉴스·공시가 없습니다.")
    if news_warning:
        st.caption(news_warning)

    st.divider()
    if st.button("주문 화면으로", type="primary", use_container_width=True, key=f"portfolio_order_{ticker}"):
        st.session_state.ade_order_ticker = ticker
        st.session_state.ade_order_symbol = name
        st.session_state.ade_primary_page = "주문"
        base_app._reset_order_confirmation()
        st.rerun()


def _render_portfolio(base_app: Any, refresh: bool) -> None:
    st.markdown("## 내 투자 현황")
    if refresh:
        base_app._cached_kis_snapshot.clear()
        account, positions, error = base_app._kis_data(True)
    else:
        account, positions, error = base_app._cached_kis_snapshot()
    if account is None:
        st.info(error or "KIS 계좌 스냅샷이 없습니다.")
        return

    selected_ticker = st.session_state.get("ade_portfolio_ticker")
    if selected_ticker:
        selected = next((row for row in positions if str(row.get("ticker")) == str(selected_ticker)), None)
        if selected is not None:
            _render_position_detail(base_app, selected)
            return
        st.session_state.ade_portfolio_ticker = None

    cash = float(account.get("cash") or 0)
    evaluation = float(account.get("evaluation_amount") or 0)
    pnl = float(account.get("pnl") or 0)
    total = float(account.get("total_assets") or 0)
    total_source = "KIS 순자산"
    if total <= 0:
        total = cash + evaluation
        total_source = "예수금+평가금액 fallback"
    invested = evaluation - pnl
    pnl_rate = pnl / invested * 100 if invested > 0 else 0.0
    for col, (label, value, delta) in zip(
        st.columns(5),
        [
            ("총자산", f"₩{total:,.0f}", None),
            ("예수금", f"₩{cash:,.0f}", None),
            ("평가금액", f"₩{evaluation:,.0f}", None),
            ("평가손익", f"₩{pnl:+,.0f}", f"{pnl_rate:+.2f}%"),
            ("보유종목", f"{int(account.get('position_count') or len(positions))}개", None),
        ],
    ):
        col.metric(label, value, delta)
    st.caption(f"총자산 기준 · {total_source}")

    st.markdown("### 보유종목")
    if not positions:
        st.info("보유종목이 없습니다.")
    for row in positions:
        ticker = _text(row, "ticker", "symbol", "code")
        name = _text(row, "name", "symbol_name", "stock_name") or ticker
        quantity = int(_number(row, "quantity", "qty", "holding_quantity"))
        pnl_value = _number(row, "pnl", "profit_loss", "evaluation_profit_loss")
        current_price = _number(row, "current_price", "price", "last_price")
        evaluation_value = _number(row, "evaluation_amount", "evaluation", "market_value")
        avg_price = _number(row, "average_price", "avg_price", "purchase_price", "buy_price")
        invested_value = avg_price * quantity if avg_price > 0 else max(0.0, evaluation_value - pnl_value)
        rate = pnl_value / invested_value * 100 if invested_value > 0 else _number(row, "pnl_rate", "profit_rate", "return_rate")
        cols = st.columns([3.2, 1.1, 1.4, 1.2])
        if cols[0].button(f"{name}\n\n{ticker}", key=f"portfolio_holding_{ticker}", use_container_width=True):
            st.session_state.ade_portfolio_ticker = ticker
            st.rerun()
        cols[1].metric("보유", f"{quantity:,}주")
        cols[2].metric("현재가", f"₩{current_price:,.0f}" if current_price else "-")
        cols[3].metric("손익", f"{rate:+.2f}%")
    if error:
        st.caption(error)


def render_overview_workspace(base_app: Any) -> None:
    st.markdown(_STICKY_KPI_STYLE, unsafe_allow_html=True)
    st.markdown("### 상황종합판")
    refresh_cols = st.columns([5, 1])
    refresh = refresh_cols[1].button("새로고침", key="overview_workspace_refresh", use_container_width=True)
    _render_market_kpis(refresh)
    st.divider()
    _render_portfolio(base_app, refresh)
    if st.session_state.get("ade_portfolio_ticker"):
        return
    st.divider()
    _render_market_context(refresh)
