from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.economic_calendar_service import load_economic_calendar
from dashboard.market_overview_service import load_market_overview, load_sector_strength
from markets.profiles import get_market_profile


_OVERVIEW_STYLE = """
<style>
.ade-board-shell{background:linear-gradient(180deg,#dff5f3 0%,#eef8ef 48%,#f4f6f8 100%);padding:16px;border-radius:30px}
.ade-board-head{display:flex;justify-content:space-between;align-items:flex-end;margin:4px 2px 14px}.ade-board-title{font-size:31px;font-weight:950;letter-spacing:-.045em;color:#0b0f14}.ade-board-sub{font-size:12px;color:#7b8794;margin-top:5px}
.ade-section-card{background:#fff;border-radius:28px;padding:24px;margin:14px 0;box-shadow:0 4px 14px rgba(22,47,66,.04)}
.ade-section-title{font-size:26px;font-weight:950;letter-spacing:-.04em;color:#0b0f14}.ade-section-sub{font-size:12px;color:#8a94a1;margin-top:5px}
.ade-market-strip{position:sticky;top:3.35rem;z-index:930;background:rgba(223,245,243,.96);backdrop-filter:blur(18px) saturate(1.15);padding:8px 0 10px;border-bottom:1px solid rgba(91,122,153,.14)}
.ade-index-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.ade-index-card{background:#fff;border-radius:22px;padding:18px;border:1px solid rgba(15,23,42,.07)}.ade-index-card .label{font-size:15px;color:#596573;font-weight:800}.ade-index-card .value{font-size:34px;font-weight:900;letter-spacing:-.05em;margin-top:7px;color:#101418}.ade-index-card .move{display:flex;gap:8px;align-items:baseline;margin-top:7px}.ade-index-card .points{font-size:16px;font-weight:850}.ade-index-card .delta{font-size:17px;font-weight:900}.ade-index-card.up .points,.ade-index-card.up .delta{color:#e5484d}.ade-index-card.down .points,.ade-index-card.down .delta{color:#2563eb}.ade-index-card.flat .points,.ade-index-card.flat .delta{color:#6b7280}.ade-index-card .mini{height:74px;margin-top:10px;position:relative;overflow:hidden;border-radius:12px;background:linear-gradient(180deg,#fbfdff,#f5f8fb);border:1px solid #edf1f5}.ade-index-card .mini .baseline{position:absolute;left:0;right:0;top:50%;border-top:1px dashed #d3dae3}.ade-index-card .mini .segment{position:absolute;height:2.5px;border-radius:999px;transform-origin:left center}.ade-index-card.up .mini .segment{background:#e5484d}.ade-index-card.down .mini .segment{background:#2563eb}.ade-index-card.flat .mini .segment{background:#7c8796}.ade-index-card .mini .dot{position:absolute;width:6px;height:6px;border-radius:50%;transform:translate(-50%,-50%)}.ade-index-card.up .mini .dot{background:#e5484d}.ade-index-card.down .mini .dot{background:#2563eb}.ade-index-card.flat .mini .dot{background:#7c8796}
.ade-portfolio-grid{display:grid;grid-template-columns:1.45fr repeat(4,1fr);gap:12px;margin-top:18px}.ade-asset-hero{background:linear-gradient(135deg,#dbeafe 0%,#e0f2fe 52%,#f0fdfa 100%);color:#0f2741;border-radius:20px;padding:18px;border:1px solid rgba(47,128,237,.14);box-shadow:0 10px 24px rgba(47,128,237,.08)}.ade-asset-hero .l{font-size:12px;color:#51708d;letter-spacing:.08em;font-weight:850}.ade-asset-hero .v{font-size:37px;font-weight:950;letter-spacing:-.05em;margin-top:6px}.ade-asset-mini{background:#fafafa;border-radius:18px;padding:16px;border:1px solid rgba(15,23,42,.06)}.ade-asset-mini .l{font-size:13px;color:#6f7b88;font-weight:800}.ade-asset-mini .v{font-size:25px;font-weight:900;margin-top:6px;letter-spacing:-.035em;color:#111827}.ade-asset-mini .s{font-size:14px;font-weight:850;margin-top:6px}.ade-asset-mini.pnl-up .v,.ade-asset-mini.pnl-up .s{color:#e5484d}.ade-asset-mini.pnl-down .v,.ade-asset-mini.pnl-down .s{color:#2563eb}.ade-asset-mini.pnl-flat .v,.ade-asset-mini.pnl-flat .s{color:#697586}
.ade-holding-row{display:grid;grid-template-columns:1.5fr .85fr 1fr 1fr 1fr;gap:12px;align-items:center;padding:16px 0;border-top:1px solid #eceff3}.ade-holding-row:first-of-type{border-top:0}.ade-holding-row .name{font-size:18px;font-weight:900}.ade-holding-row .code{font-size:10px;color:#98a2ad;margin-top:2px}.ade-holding-row .k{font-size:9px;color:#99a3ae;font-weight:800}.ade-holding-row .v{font-size:14px;font-weight:800;margin-top:3px}.ade-holding-row .rate{font-size:18px;font-weight:950;text-align:right}.ade-holding-row .rate.up{color:#e5484d}.ade-holding-row .rate.down{color:#2563eb}.ade-holding-row .rate.flat{color:#6b7280}.ade-holding-row .price{text-align:right;font-size:17px;font-weight:850}.ade-holding-row .go{text-align:right;font-size:18px;color:#a2abb5}
.ade-event-list{margin-top:16px}.ade-event-row{display:grid;grid-template-columns:86px 1fr 104px;gap:14px;align-items:start;padding:15px 0;border-top:1px solid #eceff3}.ade-event-row:first-child{border-top:0}.ade-event-row .time{font-size:11px;font-weight:850;color:#4b5563}.ade-event-row .event{font-size:16px;font-weight:780;line-height:1.35}.ade-event-row .meta{font-size:10px;color:#9aa3ad;margin-top:4px}.ade-event-row .badge{font-size:11px;font-weight:900;padding:6px 9px;border-radius:999px;text-align:center}.ade-event-row .badge.high{background:#fff3cd;color:#8a5a00;border:1px solid #f4d27a}.ade-event-row .badge.very-high{background:#ffe3e6;color:#a61b29;border:1px solid #f3a7ae}.ade-event-row .badge.normal{background:#edf2f7;color:#51606f;border:1px solid #d6dde5}
.ade-calendar-card{background:#fff;border-radius:28px;padding:24px;margin:14px 0}.ade-calendar-head{display:flex;justify-content:space-between;align-items:flex-end}.ade-calendar-title{font-size:24px;font-weight:950;letter-spacing:-.035em}.ade-calendar-sub{font-size:12px;color:#8a94a1;margin-top:5px}.ade-calendar-list{margin-top:16px}.ade-calendar-row{display:grid;grid-template-columns:96px 72px 1fr 92px;gap:14px;align-items:center;padding:14px 0;border-top:1px solid #eceff3}.ade-calendar-row:first-child{border-top:0}.ade-calendar-date{font-size:12px;font-weight:900;color:#374151}.ade-calendar-country{font-size:11px;font-weight:800;color:#7c8796}.ade-calendar-event{font-size:15px;font-weight:780;line-height:1.35}.ade-calendar-badge{font-size:10px;font-weight:900;padding:5px 8px;border-radius:999px;text-align:center}.ade-calendar-badge.high{background:#fff3cd;color:#8a5a00}.ade-calendar-badge.very-high{background:#ffe3e6;color:#a61b29}.ade-calendar-badge.normal{background:#edf2f7;color:#51606f}.ade-calendar-more{margin-top:12px;font-size:11px;color:#87919c}
.ade-sector-chip-row{display:flex;gap:9px;overflow:hidden;margin-top:16px}.ade-sector-chip{white-space:nowrap;border:1px solid #dbe1e7;border-radius:999px;padding:9px 13px;font-size:12px;font-weight:800;background:#fff}.ade-sector-list{margin-top:12px}.ade-sector-row{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-top:1px solid #eceff3}.ade-sector-row .name{font-size:15px;font-weight:850}.ade-sector-row .rate{font-size:15px;font-weight:900}.ade-source-note{font-size:10px;color:#9aa3ad;margin-top:8px}
@media(max-width:900px){.ade-index-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ade-portfolio-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ade-asset-hero{grid-column:1/-1}.ade-holding-row{grid-template-columns:1.5fr 1fr 1fr}.ade-holding-row .hide-mobile{display:none}.ade-event-row{grid-template-columns:76px 1fr 82px}.ade-calendar-row{grid-template-columns:84px 1fr 78px}.ade-calendar-country{display:none}}
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


def _event_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    preferred = ["일시(KST)", "국가", "구분", "이벤트", "중요도", "출처", "비고"]
    return frame[[column for column in preferred if column in frame.columns]]


def _load_overview_data(base_app: Any, refresh: bool):
    metrics, metric_warning = load_market_overview(refresh=refresh)
    rows, event_warning = load_economic_calendar(days_ahead=90, refresh=refresh)
    important = [row for row in rows if str(row.get("중요도") or "") in {"높음", "매우 높음"}]
    if refresh:
        base_app._cached_kis_snapshot.clear()
        account, positions, account_warning = base_app._kis_data(True)
    else:
        account, positions, account_warning = base_app._cached_kis_snapshot()
    sectors, sector_warning = load_sector_strength(get_market_profile("kr").db_path, limit=6, refresh=refresh)
    warnings = [w for w in [metric_warning, event_warning, account_warning, sector_warning] if w]
    return metrics, account, positions, important, rows, sectors, warnings


def _metric_parts(metrics: dict[str, Any], key: str) -> tuple[str, str, float, float, str]:
    metric = metrics.get(key)
    label = metric.label if metric else key.upper()
    if metric is None or metric.value is None:
        return label, "조회 실패", 0.0, 0.0, "flat"
    change_rate = float(metric.change_rate or 0.0)
    change = float(getattr(metric, "change", 0.0) or 0.0)
    if change == 0.0 and change_rate != 0.0 and metric.value:
        previous = float(metric.value) / (1.0 + change_rate / 100.0) if change_rate > -100 else float(metric.value)
        change = float(metric.value) - previous
    tone = "up" if change_rate > 0 else ("down" if change_rate < 0 else "flat")
    return label, f"{metric.value:,.2f}", change, change_rate, tone


def _sparkline_html(history: tuple[float, ...] | list[float] | None) -> str:
    values = [float(value) for value in (history or []) if value is not None]
    if len(values) < 2:
        return '<div class="baseline"></div>'

    low = min(values)
    high = max(values)
    span = high - low
    if span <= 0:
        ys = [50.0 for _ in values]
    else:
        ys = [84.0 - ((value - low) / span) * 68.0 for value in values]

    xs = [4.0 + i * (92.0 / (len(values) - 1)) for i in range(len(values))]
    segments: list[str] = ['<div class="baseline"></div>']
    for i in range(len(xs) - 1):
        x1, x2 = xs[i], xs[i + 1]
        y1, y2 = ys[i], ys[i + 1]
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        angle = __import__('math').degrees(__import__('math').atan2(dy, dx))
        segments.append(
            f'<span class="segment" style="left:{x1:.2f}%;top:{y1:.2f}%;width:{length:.2f}%;transform:rotate({angle:.2f}deg)"></span>'
        )
    segments.append(f'<span class="dot" style="left:{xs[-1]:.2f}%;top:{ys[-1]:.2f}%"></span>')
    return ''.join(segments)


def _render_market_strip(metrics: dict[str, Any]) -> None:
    ordered = ["kospi", "kosdaq", "sp500", "nasdaq", "usdkrw", "vix"]
    cards = []
    for key in ordered:
        metric = metrics.get(key)
        label, value, change, change_rate, tone = _metric_parts(metrics, key)
        arrow = "▲" if tone == "up" else ("▼" if tone == "down" else "•")
        points = f"{change:+,.2f}" if value != "조회 실패" else "-"
        delta = f"{change_rate:+.2f}%" if value != "조회 실패" else "-"
        history = getattr(metric, "history", ()) if metric is not None else ()
        cards.append(
            f'<div class="ade-index-card {tone}"><div class="label">{label} · 실시간</div><div class="value">{value}</div><div class="move"><div class="points">{arrow} {points}</div><div class="delta">({delta})</div></div><div class="mini">{_sparkline_html(history)}</div></div>'
        )
    st.markdown('<div class="ade-market-strip"><div class="ade-index-grid">' + ''.join(cards) + '</div></div>', unsafe_allow_html=True)


def _render_portfolio_summary(account: dict[str, Any] | None, positions: list[dict[str, Any]]) -> None:
    total = float((account or {}).get("total_assets") or 0)
    cash = float((account or {}).get("cash") or 0)
    evaluation = float((account or {}).get("evaluation_amount") or 0)
    pnl = float((account or {}).get("pnl") or 0)
    if total <= 0:
        total = cash + evaluation
    invested = evaluation - pnl
    pnl_rate = pnl / invested * 100 if invested > 0 else 0.0
    count = int((account or {}).get("position_count") or len(positions))
    pnl_class = "pnl-up" if pnl_rate > 0 else ("pnl-down" if pnl_rate < 0 else "pnl-flat")
    st.markdown(f'''<div class="ade-section-card"><div class="ade-section-title">내 투자 현황</div><div class="ade-section-sub">계좌 전체 상태를 먼저 보고, 아래 보유종목에서 상세 판단으로 이동합니다.</div><div class="ade-portfolio-grid"><div class="ade-asset-hero"><div class="l">TOTAL ASSETS</div><div class="v">₩{total:,.0f}</div></div><div class="ade-asset-mini"><div class="l">예수금</div><div class="v">₩{cash:,.0f}</div></div><div class="ade-asset-mini"><div class="l">평가금액</div><div class="v">₩{evaluation:,.0f}</div></div><div class="ade-asset-mini {pnl_class}"><div class="l">평가손익</div><div class="v">₩{pnl:+,.0f}</div><div class="s">{pnl_rate:+.2f}%</div></div><div class="ade-asset-mini"><div class="l">보유종목</div><div class="v">{count}개</div></div></div></div>''', unsafe_allow_html=True)


def _render_holdings(positions: list[dict[str, Any]]) -> None:
    st.markdown('<div class="ade-section-card"><div class="ade-section-title">보유종목</div><div class="ade-section-sub">가격·수익률을 한눈에 보고 종목을 눌러 상세 분석으로 들어갑니다.</div>', unsafe_allow_html=True)
    if not positions:
        st.markdown('<div style="padding:18px 0;color:#8a94a1">보유종목이 없습니다.</div></div>', unsafe_allow_html=True)
        return
    for row in positions:
        ticker = _text(row, "ticker")
        name = _text(row, "name", "ticker")
        qty = int(_number(row, "quantity"))
        avg = _number(row, "average_price")
        current = _number(row, "current_price")
        rate = _number(row, "pnl_rate")
        tone = "up" if rate > 0 else ("down" if rate < 0 else "flat")
        st.markdown(f'''<div class="ade-holding-row"><div><div class="name">{name}</div><div class="code">{ticker}</div></div><div class="hide-mobile"><div class="k">보유</div><div class="v">{qty:,}주</div></div><div class="hide-mobile"><div class="k">평단</div><div class="v">₩{avg:,.0f}</div></div><div><div class="k">현재가</div><div class="price">₩{current:,.0f}</div></div><div><div class="k">수익률</div><div class="rate {tone}">{rate:+.2f}%</div></div></div>''', unsafe_allow_html=True)
        if st.button(f"{name} 상세보기", key=f"overview_holding_{ticker}", use_container_width=True):
            st.session_state.ade_portfolio_ticker = ticker
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _importance_class(value: str) -> str:
    value = str(value or "")
    if value == "매우 높음":
        return "very-high"
    if value == "높음":
        return "high"
    return "normal"


def _render_events(important: list[dict[str, Any]]) -> None:
    st.markdown('<div class="ade-section-card"><div class="ade-section-title">오늘 시장에서 봐야 할 것</div><div class="ade-section-sub">중요 이벤트만 크게 읽도록 정리했습니다.</div><div class="ade-event-list">', unsafe_allow_html=True)
    if important:
        for row in important[:5]:
            when = str(row.get("일시(KST)") or "-")
            country = str(row.get("국가") or "-")
            event = str(row.get("이벤트") or row.get("구분") or "-")
            importance = str(row.get("중요도") or "-")
            source = str(row.get("출처") or "")
            css = _importance_class(importance)
            st.markdown(f'<div class="ade-event-row"><div class="time">{when}<div class="meta">{country}</div></div><div class="event">{event}<div class="meta">{source}</div></div><div class="badge {css}">{importance}</div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="padding:16px 0;color:#8a94a1">표시할 주요 이벤트가 없습니다.</div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)


def _render_90_day_calendar(rows: list[dict[str, Any]]) -> None:
    st.markdown('<div class="ade-calendar-card"><div class="ade-calendar-head"><div><div class="ade-calendar-title">90일 주요 일정</div><div class="ade-calendar-sub">앞으로 90일의 주요 경제 이벤트를 시간순으로 확인합니다.</div></div></div><div class="ade-calendar-list">', unsafe_allow_html=True)
    if rows:
        for row in rows[:12]:
            when = str(row.get("일시(KST)") or "-")
            country = str(row.get("국가") or "-")
            event = str(row.get("이벤트") or row.get("구분") or "-")
            importance = str(row.get("중요도") or "-")
            css = _importance_class(importance)
            st.markdown(f'<div class="ade-calendar-row"><div class="ade-calendar-date">{when}</div><div class="ade-calendar-country">{country}</div><div class="ade-calendar-event">{event}</div><div class="ade-calendar-badge {css}">{importance}</div></div>', unsafe_allow_html=True)
        if len(rows) > 12:
            st.markdown(f'<div class="ade-calendar-more">외 {len(rows) - 12}개 일정</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="padding:16px 0;color:#8a94a1">표시할 일정이 없습니다.</div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)


def _render_sectors(sectors: list[dict[str, Any]]) -> None:
    st.markdown('<div class="ade-section-card"><div class="ade-section-title">국내 섹터 흐름</div><div class="ade-section-sub">강한 업종과 약한 업종을 상대강도로 봅니다.</div><div class="ade-sector-list">', unsafe_allow_html=True)
    if sectors:
        for row in sectors:
            name = str(row.get("sector") or "-")
            rate = _number(row, "change_rate", "relative_strength")
            tone = "up" if rate > 0 else ("down" if rate < 0 else "flat")
            st.markdown(f'<div class="ade-sector-row"><div class="name">{name}</div><div class="rate {tone}">{rate:+.2f}%</div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="padding:16px 0;color:#8a94a1">표시할 섹터 데이터가 없습니다.</div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)


def _render_position_detail(base_app: Any, holding: dict[str, Any]) -> None:
    ticker = _text(holding, "ticker")
    name = _text(holding, "name", "ticker")
    if st.button("← 상황종합판으로", key=f"portfolio_back_{ticker}"):
        st.session_state.ade_portfolio_ticker = None
        st.rerun()
    st.markdown(f"## {name} · 보유종목 검증")
    qty = int(_number(holding, "quantity"))
    avg = _number(holding, "average_price")
    current_price = _number(holding, "current_price")
    rate = _number(holding, "pnl_rate")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("보유수량", f"{qty:,}주")
    c2.metric("평균매입가", f"₩{avg:,.0f}")
    c3.metric("현재가", f"₩{current_price:,.0f}")
    c4.metric("수익률", f"{rate:+.2f}%")

    profile = get_market_profile("kr")
    normalized_ticker = base_app.normalize_ticker(ticker, "kr")
    with base_app.sqlite3.connect(str(profile.db_path), timeout=5) as conn:
        conn.row_factory = base_app.sqlite3.Row
        current, source, warning = base_app._load_current_bars_resilient(conn, "kr", normalized_ticker, profile.price_source)
    if warning:
        st.caption(warning)
    if not current.empty:
        chart = base_app.build_trading_chart(current, name)
        try:
            chart.add_hline(y=avg, line_dash="dot", annotation_text=f"평단 {avg:,.0f}")
        except Exception:
            pass
        st.plotly_chart(chart, use_container_width=True, config=base_app.CHART_CONFIG)
    else:
        st.info("현재 가격 차트를 불러오지 못했습니다.")

    supply = base_app.load_supply_demand_health(normalized_ticker, market="kr")
    st.markdown("### 수급·환경")
    st.write(str((supply.get("investor") or {}).get("detail") or "수급 데이터 확인 필요"))

    recommendations, context = base_app._load_recommendations("kr")
    recommendation = next((row for row in recommendations if str(row.get("ticker")) == ticker), None)
    st.markdown("### ADE 추천 상태")
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


def render_overview_workspace(base_app: Any) -> None:
    st.markdown(_OVERVIEW_STYLE, unsafe_allow_html=True)
    refresh_cols = st.columns([5, 1])
    refresh = refresh_cols[1].button("새로고침", key="overview_workspace_refresh", use_container_width=True)
    metrics, account, positions, important, rows, sectors, warnings = _load_overview_data(base_app, refresh)

    selected_ticker = st.session_state.get("ade_portfolio_ticker")
    if selected_ticker:
        selected = next((row for row in positions if str(row.get("ticker")) == str(selected_ticker)), None)
        if selected is not None:
            _render_position_detail(base_app, selected)
            return
        st.session_state.ade_portfolio_ticker = None

    st.markdown('<div class="ade-board-shell"><div class="ade-board-head"><div><div class="ade-board-title">상황종합판</div><div class="ade-board-sub">#43 Reference Replica + #45 Editorial Cards 통합안</div></div></div>', unsafe_allow_html=True)
    _render_market_strip(metrics)
    _render_portfolio_summary(account, positions)
    _render_holdings(positions)
    _render_events(important)
    _render_90_day_calendar(rows)
    _render_sectors(sectors)
    st.markdown('</div>', unsafe_allow_html=True)

    for warning in warnings:
        st.caption(str(warning))
