from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.economic_calendar_service import load_economic_calendar
from dashboard.market_overview_service import load_market_overview, load_sector_strength
from markets.profiles import get_market_profile


_STICKY_KPI_STYLE = """
<style>
.ade-market-strip{position:sticky;top:3.35rem;z-index:930;padding:.55rem 0 .7rem;background:rgba(247,251,255,.94);backdrop-filter:blur(18px) saturate(1.2);border-bottom:1px solid rgba(91,122,153,.18)}
.ade-design-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}.ade-design-card{min-height:104px;border-radius:16px;padding:13px 14px;box-sizing:border-box}.ade-design-no{font-size:10px;font-weight:900;letter-spacing:.08em;opacity:.62}.ade-design-title{font-size:9px;font-weight:800;opacity:.58;margin-top:2px}.ade-design-label{font-size:11px;font-weight:800;margin-top:8px}.ade-design-value{line-height:1;margin-top:5px}.ade-design-delta{font-size:11px;margin-top:7px;font-weight:800}.d1{background:#0d1b2a;color:#fff;border:1px solid #20364c}.d1 .ade-design-value{font-size:29px;font-weight:950}.d2{background:transparent;border:0;border-bottom:3px solid #2f80ed;border-radius:0;color:#0b1f33}.d2 .ade-design-label{font-size:10px;font-weight:500;letter-spacing:.12em}.d2 .ade-design-value{font-size:25px;font-weight:650}.d3{background:#fff;color:#17212b;border:1px solid rgba(42,57,73,.16);box-shadow:0 6px 18px rgba(21,34,47,.07)}.d3 .ade-design-value{font-size:23px;font-weight:800}.d4{background:#111820;color:#f4f6f8;border-radius:5px;border-left:4px solid #f4a340}.d4 .ade-design-value{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:22px;font-weight:900}.d5{background:linear-gradient(135deg,#eef6ff,#fff);color:#102033;border:1px solid rgba(36,99,235,.18)}.d5 .ade-design-value{font-size:30px;font-weight:500;letter-spacing:-.06em}.d6{background:linear-gradient(180deg,#fff7ed,#fff);color:#6b3a00;border:1px solid rgba(201,130,0,.22)}.d6 .ade-design-label{font-size:12px;font-weight:900}.d6 .ade-design-value{font-size:27px;font-weight:950}.d6 .ade-design-delta{display:inline-block;padding:3px 7px;border-radius:999px;background:rgba(201,130,0,.10)}
.portfolio-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.p-card{min-height:118px;padding:15px;border-radius:18px}.p1{background:linear-gradient(135deg,#0b1f33,#173e63);color:white}.p1 .v{font-size:30px;font-weight:950}.p2{background:#fff;border:1px dashed rgba(47,128,237,.42)}.p2 .v{font-size:24px;font-weight:650}.p3{background:rgba(255,255,255,.64);border:1px solid rgba(91,122,153,.20);box-shadow:inset 0 0 0 1px rgba(255,255,255,.65)}.p3 .v{font-size:22px;font-weight:850}.p4{background:#0d1b2a;color:white;border-left:5px solid #e5484d;border-radius:8px}.p4 .v{font-size:26px;font-weight:950}.p5{background:linear-gradient(180deg,#f8fafc,#eef2f7);border:1px solid rgba(71,85,105,.16)}.p5 .v{font-size:34px;font-weight:400}.p-card .n{font-size:10px;font-weight:900;opacity:.62}.p-card .t{font-size:10px;font-weight:800;opacity:.58;margin-bottom:8px}.p-card .l{font-size:11px;font-weight:800;opacity:.7}.p-card .v{margin-top:5px;letter-spacing:-.04em}.p-card .s{font-size:11px;margin-top:7px;font-weight:800}
.holding-card{display:grid;grid-template-columns:1.6fr .8fr 1fr 1fr 1fr;gap:14px;align-items:center;padding:15px 16px;margin:8px 0;border-radius:14px;background:linear-gradient(90deg,#fff,#f6fbff);border:1px solid rgba(91,122,153,.18);box-shadow:0 7px 20px rgba(35,76,118,.06)}.holding-card .name{font-size:18px;font-weight:950}.holding-card .code{font-size:10px;opacity:.58}.holding-card .k{font-size:9px;font-weight:800;opacity:.55}.holding-card .v{font-size:15px;font-weight:850;margin-top:2px}.event-card{display:grid;grid-template-columns:86px 72px 1fr 78px;gap:12px;align-items:center;padding:12px 14px;margin:7px 0;border-radius:12px;border:1px solid rgba(91,122,153,.16);background:#fff}.event-card .date{font-size:12px;font-weight:900}.event-card .country{font-size:11px;font-weight:800;opacity:.65}.event-card .event{font-size:13px;font-weight:800}.event-card .importance{font-size:10px;font-weight:900;padding:4px 7px;border-radius:999px;background:rgba(229,72,77,.09);text-align:center}
.design-section-label{margin:18px 0 8px;font-size:11px;font-weight:950;letter-spacing:.12em;color:#5f7287;text-transform:uppercase}
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
    ordered = [
        ("kospi", 1, "Institutional Bold"),
        ("kosdaq", 2, "Minimal Underline"),
        ("sp500", 3, "FactSet Clean"),
        ("nasdaq", 4, "Terminal Mono"),
        ("usdkrw", 5, "FX Airy"),
        ("vix", 6, "Risk Badge"),
    ]
    cards = []
    for key, no, title in ordered:
        metric = metrics.get(key)
        label = metric.label if metric else key.upper()
        value = "조회 실패" if metric is None or metric.value is None else f"{metric.value:,.2f}"
        delta = "-" if metric is None or metric.change_rate is None else f"{metric.change_rate:+.2f}%"
        cards.append(
            f'<div class="ade-design-card d{no}"><div class="ade-design-no">#{no}</div><div class="ade-design-title">{title}</div><div class="ade-design-label">{label}</div><div class="ade-design-value">{value}</div><div class="ade-design-delta">{delta}</div></div>'
        )
    st.markdown('<div class="ade-market-strip"><div class="ade-design-grid">' + "".join(cards) + '</div></div>', unsafe_allow_html=True)
    if warning:
        st.caption(warning)


def _event_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    preferred = ["일시(KST)", "국가", "구분", "이벤트", "중요도", "출처", "비고"]
    return frame[[column for column in preferred if column in frame.columns]]


def _render_market_context(refresh: bool) -> None:
    rows, warning = load_economic_calendar(days_ahead=90, refresh=refresh)
    important = [row for row in rows if str(row.get("중요도") or "") in {"높음", "매우 높음"}]
    st.markdown('<div class="design-section-label">#13 Event Timeline · 주요 이벤트</div>', unsafe_allow_html=True)
    if important:
        for row in important[:5]:
            date = str(row.get("일시(KST)") or "-")
            country = str(row.get("국가") or "-")
            event = str(row.get("이벤트") or row.get("구분") or "-")
            importance = str(row.get("중요도") or "-")
            st.markdown(f'<div class="event-card"><div class="date">{date}</div><div class="country">{country}</div><div class="event">{event}</div><div class="importance">{importance}</div></div>', unsafe_allow_html=True)
    else:
        st.info("표시할 주요 이벤트가 없습니다.")
    if warning:
        st.caption(warning)
    with st.expander("향후 90일 전체 일정", expanded=False):
        if rows:
            st.dataframe(_event_frame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("표시할 전체 이벤트가 없습니다.")

    st.markdown('<div class="design-section-label">#14 Sector Table · 국내 업종 등락 순위</div>', unsafe_allow_html=True)
    sectors, sector_warning = load_sector_strength(get_market_profile("kr").db_path, limit=10, refresh=refresh)
    if sectors:
        frame = pd.DataFrame(sectors)
        display = pd.DataFrame({"업종": frame.get("sector"), "등락률(%)": frame.get("change_rate"), "거래대금": frame.get("turnover"), "기준일": frame.get("as_of"), "출처": frame.get("source")})
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
        current, source, chart_warning = base_app._load_current_bars_resilient(conn, "kr", normalized, profile.price_source)
    if current.empty:
        st.info("표시할 가격 이력이 없습니다.")
    else:
        chart = base_app.build_trading_chart(current, f"{name} · {ticker}", height=680)
        if avg_price > 0:
            chart.add_hline(y=avg_price, line_dash="dash", annotation_text=f"내 평균매입가 {avg_price:,.0f}", row=1, col=1)
        st.plotly_chart(chart, use_container_width=True, config=base_app.CHART_CONFIG, key=f"portfolio_chart_{ticker}")
    st.caption(f"가격소스 {source}")
    if chart_warning:
        st.caption(chart_warning)
    st.markdown("### 수급")
    supply = base_app.load_supply_demand_health(normalized, market="kr")
    investor = supply.get("investor") if isinstance(supply, dict) else None
    st.info(str((investor or {}).get("detail") or "수급 세부정보가 없습니다."))
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
    portfolio_cards = [
        (7, "Asset Hero", "총자산", f"₩{total:,.0f}", total_source),
        (8, "Cash Outline", "예수금", f"₩{cash:,.0f}", "가용 현금"),
        (9, "Glass Balance", "평가금액", f"₩{evaluation:,.0f}", "보유 평가"),
        (10, "P&L Alert", "평가손익", f"₩{pnl:+,.0f}", f"{pnl_rate:+.2f}%"),
        (11, "Count Minimal", "보유종목", f"{int(account.get('position_count') or len(positions))}개", "포지션"),
    ]
    html = []
    for no, title, label, value, sub in portfolio_cards:
        html.append(f'<div class="p-card p{no-6}"><div class="n">#{no}</div><div class="t">{title}</div><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div></div>')
    st.markdown('<div class="portfolio-grid">' + "".join(html) + '</div>', unsafe_allow_html=True)
    st.markdown('<div class="design-section-label">#12 Position Row · 보유종목</div>', unsafe_allow_html=True)
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
        st.markdown(f'<div class="holding-card"><div><div class="name">{name}</div><div class="code">{ticker}</div></div><div><div class="k">보유</div><div class="v">{quantity:,}주</div></div><div><div class="k">평단</div><div class="v">₩{avg_price:,.0f}</div></div><div><div class="k">현재가</div><div class="v">₩{current_price:,.0f}</div></div><div><div class="k">손익</div><div class="v">{rate:+.2f}%</div></div></div>', unsafe_allow_html=True)
        if st.button(f"{name} 상세 열기", key=f"portfolio_holding_{ticker}", use_container_width=True):
            st.session_state.ade_portfolio_ticker = ticker
            st.rerun()
    if error:
        st.caption(error)


def render_overview_workspace(base_app: Any) -> None:
    st.markdown(_STICKY_KPI_STYLE, unsafe_allow_html=True)
    st.markdown("### 상황종합판 · UI Design Test")
    refresh_cols = st.columns([5, 1])
    refresh = refresh_cols[1].button("새로고침", key="overview_workspace_refresh", use_container_width=True)
    _render_market_kpis(refresh)
    st.divider()
    _render_portfolio(base_app, refresh)
    if st.session_state.get("ade_portfolio_ticker"):
        return
    st.divider()
    _render_market_context(refresh)
