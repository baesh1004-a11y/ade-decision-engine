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
.ade-design-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}.ade-design-card{min-height:104px;padding:13px 14px;box-sizing:border-box}.ade-design-no{font-size:10px;font-weight:900;letter-spacing:.08em;opacity:.62}.ade-design-title{font-size:9px;font-weight:800;opacity:.58;margin-top:2px}.ade-design-label{font-size:11px;margin-top:8px}.ade-design-value{line-height:1;margin-top:5px}.ade-design-delta{font-size:11px;margin-top:7px;font-weight:800}
.d15{background:linear-gradient(135deg,#0f2741,#1a4e7a);color:white;border-radius:22px}.d15 .ade-design-label{font-weight:500;letter-spacing:.16em}.d15 .ade-design-value{font-size:31px;font-weight:900}.d16{background:#fff;color:#111827;border-radius:2px;border-top:4px solid #111827}.d16 .ade-design-label{font-size:9px;font-weight:900;text-transform:uppercase}.d16 .ade-design-value{font-size:28px;font-weight:300}.d17{background:linear-gradient(180deg,#eef7ff,#ffffff);color:#16324f;border-radius:14px;border:1px solid rgba(47,128,237,.18);box-shadow:0 12px 28px rgba(47,128,237,.08)}.d17 .ade-design-value{font-size:24px;font-weight:950}.d17 .ade-design-delta{font-weight:500}.d18{background:#05080d;color:#d7f7e8;border-radius:0;border:1px solid #1d2a36}.d18 .ade-design-label{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;font-weight:700}.d18 .ade-design-value{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:23px;font-weight:800;letter-spacing:.02em}.d19{background:#fdfdfd;color:#0b1f33;border-radius:20px;border:1px solid rgba(91,122,153,.12)}.d19 .ade-design-label{font-size:12px;font-weight:400}.d19 .ade-design-value{font-size:32px;font-weight:700;letter-spacing:-.06em}.d19 .ade-design-delta{opacity:.55}.d20{background:linear-gradient(135deg,#fff1f2,#fff);color:#7f1d1d;border-radius:30px;border:1px solid rgba(225,29,72,.16)}.d20 .ade-design-label{font-size:10px;font-weight:950}.d20 .ade-design-value{font-size:27px;font-weight:950}.d20 .ade-design-delta{display:inline-block;padding:3px 8px;border-radius:999px;background:rgba(225,29,72,.08)}
.portfolio-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.p-card{min-height:118px;padding:15px}.p-card .n{font-size:10px;font-weight:900;opacity:.62}.p-card .t{font-size:10px;font-weight:800;opacity:.58;margin-bottom:8px}.p-card .l{font-size:11px;opacity:.7}.p-card .v{margin-top:5px;letter-spacing:-.04em}.p-card .s{font-size:11px;margin-top:7px;font-weight:800}
.p21{background:#07111f;color:white;border-radius:24px}.p21 .l{font-size:10px;font-weight:500;letter-spacing:.14em}.p21 .v{font-size:34px;font-weight:950}.p22{background:#fff;border-left:6px solid #2f80ed;border-radius:8px;box-shadow:0 6px 18px rgba(47,128,237,.08)}.p22 .v{font-size:23px;font-weight:500}.p23{background:linear-gradient(135deg,rgba(255,255,255,.88),rgba(220,239,255,.56));border:1px solid rgba(91,122,153,.16);border-radius:26px;backdrop-filter:blur(16px)}.p23 .v{font-size:25px;font-weight:850}.p24{background:#fff7ed;border-radius:14px;border:1px solid rgba(249,115,22,.22)}.p24 .l{font-weight:900;color:#9a3412}.p24 .v{font-size:29px;font-weight:950;color:#9a3412}.p24 .s{font-size:13px}.p25{background:#f8fafc;border-radius:2px;border-top:1px solid #94a3b8;border-bottom:1px solid #94a3b8}.p25 .l{font-size:9px;font-weight:900;letter-spacing:.12em}.p25 .v{font-size:36px;font-weight:300}
.holding-card{display:grid;grid-template-columns:1.4fr .8fr .95fr 1fr 1fr;gap:14px;align-items:center;padding:15px 16px;margin:8px 0;background:#08111c;color:white;border-radius:18px;border:1px solid #223247}.holding-card .name{font-size:20px;font-weight:900}.holding-card .code{font-size:10px;opacity:.5;letter-spacing:.12em}.holding-card .k{font-size:9px;font-weight:700;opacity:.5}.holding-card .v{font-size:15px;font-weight:800;margin-top:2px}.holding-card .rate{font-size:20px;font-weight:950}
.event-card{display:grid;grid-template-columns:72px 62px 1fr 92px;gap:12px;align-items:center;padding:13px 14px;margin:7px 0;border-left:4px solid #2f80ed;background:linear-gradient(90deg,#f7fbff,#fff);border-radius:6px;box-shadow:0 4px 12px rgba(35,76,118,.05)}.event-card .date{font-size:11px;font-weight:950;line-height:1.35}.event-card .country{font-size:10px;font-weight:900;opacity:.62;text-transform:uppercase}.event-card .event{font-size:14px;font-weight:700}.event-card .importance{font-size:10px;font-weight:950;padding:5px 8px;border-radius:6px;background:#0b1f33;color:#fff;text-align:center}
.sector-card{display:grid;grid-template-columns:1.5fr .7fr 1fr .8fr;gap:12px;align-items:center;padding:12px 14px;margin:7px 0;border-radius:16px;background:#fff;border:1px solid rgba(91,122,153,.16)}.sector-card .name{font-size:14px;font-weight:900}.sector-card .rate{font-size:18px;font-weight:950}.sector-card .meta{font-size:10px;opacity:.6}.design-section-label{margin:18px 0 8px;font-size:11px;font-weight:950;letter-spacing:.12em;color:#5f7287;text-transform:uppercase}
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
        ("kospi", 15, "Executive Gradient"),
        ("kosdaq", 16, "Editorial Light"),
        ("sp500", 17, "Soft Research"),
        ("nasdaq", 18, "Code Terminal"),
        ("usdkrw", 19, "Premium Air"),
        ("vix", 20, "Risk Capsule"),
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
    st.markdown('<div class="design-section-label">#27 Signal Rail · 주요 이벤트</div>', unsafe_allow_html=True)
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

    st.markdown('<div class="design-section-label">#28 Sector Tiles · 국내 업종 등락 순위</div>', unsafe_allow_html=True)
    sectors, sector_warning = load_sector_strength(get_market_profile("kr").db_path, limit=10, refresh=refresh)
    if sectors:
        for row in sectors:
            sector = str(row.get("sector") or "-")
            rate = _number(row, "change_rate")
            turnover = _number(row, "turnover")
            as_of = str(row.get("as_of") or "-")
            st.markdown(f'<div class="sector-card"><div class="name">{sector}</div><div class="rate">{rate:+.2f}%</div><div class="meta">거래대금 {turnover:,.0f}</div><div class="meta">{as_of}</div></div>', unsafe_allow_html=True)
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
    cards = [
        (21, "Hero Ledger", "총자산", f"₩{total:,.0f}", total_source),
        (22, "Cash Spine", "예수금", f"₩{cash:,.0f}", "가용 현금"),
        (23, "Frosted NAV", "평가금액", f"₩{evaluation:,.0f}", "보유자산 평가"),
        (24, "P&L Focus", "평가손익", f"₩{pnl:+,.0f}", f"{pnl_rate:+.2f}%"),
        (25, "Count Ledger", "보유종목", f"{int(account.get('position_count') or len(positions))}개", "현재 포지션"),
    ]
    html = []
    for no, title, label, value, sub in cards:
        html.append(f'<div class="p-card p{no}"><div class="n">#{no}</div><div class="t">{title}</div><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div></div>')
    st.markdown('<div class="portfolio-grid">' + "".join(html) + '</div>', unsafe_allow_html=True)

    st.markdown('<div class="design-section-label">#26 Dark Position Strip · 보유종목</div>', unsafe_allow_html=True)
    if not positions:
        st.info("보유종목이 없습니다.")
    for row in positions:
        ticker = _text(row, "ticker", "symbol", "code")
        name = _text(row, "name", "symbol_name", "stock_name") or ticker
        quantity = int(_number(row, "quantity", "qty", "holding_quantity"))
        avg_price = _number(row, "average_price", "avg_price", "purchase_price", "buy_price")
        current_price = _number(row, "current_price", "price", "last_price")
        pnl_value = _number(row, "pnl", "profit_loss", "evaluation_profit_loss")
        evaluation_value = _number(row, "evaluation_amount", "evaluation", "market_value")
        invested_value = avg_price * quantity if avg_price > 0 else max(0.0, evaluation_value - pnl_value)
        rate = pnl_value / invested_value * 100 if invested_value > 0 else _number(row, "pnl_rate", "profit_rate", "return_rate")
        st.markdown(
            f'<div class="holding-card"><div><div class="name">{name}</div><div class="code">{ticker}</div></div><div><div class="k">보유</div><div class="v">{quantity:,}주</div></div><div><div class="k">평단</div><div class="v">₩{avg_price:,.0f}</div></div><div><div class="k">현재가</div><div class="v">₩{current_price:,.0f}</div></div><div><div class="k">수익률</div><div class="rate">{rate:+.2f}%</div></div></div>',
            unsafe_allow_html=True,
        )
        if st.button(f"{name} 상세보기", key=f"portfolio_holding_{ticker}", use_container_width=True):
            st.session_state.ade_portfolio_ticker = ticker
            st.rerun()
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
