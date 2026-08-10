from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.economic_calendar_service import load_economic_calendar
from dashboard.market_overview_service import load_market_overview, load_sector_strength
from markets.profiles import get_market_profile


_STICKY_KPI_STYLE = """
<style>
.ade-market-strip{position:sticky;top:3.35rem;z-index:930;padding:.55rem 0 .7rem;background:rgba(236,249,247,.96);backdrop-filter:blur(18px) saturate(1.2);border-bottom:1px solid rgba(91,122,153,.18)}
.design-section-label{margin:18px 0 8px;font-size:10px;font-weight:950;letter-spacing:.12em;color:#5f7287;text-transform:uppercase}

/* #43 Reference Replica */
.ref-shell{background:linear-gradient(180deg,#dff5f3 0%,#eef8ef 52%,#f3f4f7 100%);padding:14px;border-radius:28px}.ref-card{background:#fff;border-radius:28px;padding:24px;margin:14px 0;box-shadow:0 3px 10px rgba(22,47,66,.03)}.ref-title{font-size:25px;font-weight:950;letter-spacing:-.04em;color:#0b0f14}.ref-chip-row{display:flex;gap:10px;overflow:hidden;margin-top:18px}.ref-chip{white-space:nowrap;border:1px solid rgba(15,23,42,.12);border-radius:999px;padding:10px 14px;font-size:13px;font-weight:750;background:#fff}.ref-chip.active{border:2px solid #111827;color:#111827}.ref-soft{background:#fafafa;border-radius:18px;padding:20px;margin-top:18px}.ref-kpi-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.ref-index{background:#fff;border-radius:24px;padding:20px}.ref-index .label{font-size:14px;color:#6b7280}.ref-index .value{font-size:30px;font-weight:700;margin-top:8px}.ref-index .delta{font-size:16px;font-weight:700;margin-top:6px;color:#e5484d}.ref-mini{height:54px;border-bottom:1px dashed #b8c0ca;margin:10px 0 8px;position:relative}.ref-mini:after{content:"";position:absolute;left:12%;right:18%;top:34px;height:2px;background:linear-gradient(90deg,#aab2bd 0 45%,#e5484d 45% 100%);transform:skewY(-8deg)}

/* #44 Brokerage Clean */
.b44{background:#fff;border-radius:22px;padding:20px;border:1px solid rgba(91,122,153,.12)}.b44 h3{font-size:22px;margin:0 0 16px}.b44-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.b44-item{padding:14px 0;border-top:1px solid rgba(15,23,42,.08)}.b44-item .l{font-size:11px;color:#7b8794}.b44-item .v{font-size:26px;font-weight:800;margin-top:3px}.b44-row{display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-top:1px solid rgba(15,23,42,.08)}.b44-row .name{font-size:18px;font-weight:850}.b44-row .meta{font-size:11px;color:#8a94a1}.b44-row .right{text-align:right}.b44-row .price{font-size:20px;font-weight:800}.b44-row .rate{font-size:13px;font-weight:800;color:#e5484d}

/* #45 Editorial Cards */
.b45{background:#f8fafc;border-radius:18px;padding:18px}.b45-head{font-size:28px;font-weight:950;line-height:1.05}.b45-sub{font-size:12px;color:#7c8796;margin-top:6px}.b45-list{margin-top:16px}.b45-line{display:grid;grid-template-columns:76px 1fr 90px;gap:12px;align-items:start;padding:14px 0;border-top:1px solid #e5e7eb}.b45-line .time{font-size:12px;font-weight:850}.b45-line .event{font-size:16px;font-weight:750}.b45-line .badge{font-size:10px;font-weight:900;padding:4px 7px;border-radius:999px;background:#111827;color:#fff;text-align:center}

/* #46 Data Dense */
.b46{background:#0b1219;color:#e8eef4;border-radius:12px;padding:16px}.b46-title{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;font-weight:900;letter-spacing:.08em}.b46-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:6px;margin-top:10px}.b46-cell{border:1px solid #243241;padding:9px;border-radius:6px}.b46-cell .l{font-size:8px;color:#8fa0af}.b46-cell .v{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:18px;font-weight:850;margin-top:3px}.b46-cell .d{font-size:9px;color:#9dd7bd;margin-top:3px}

/* #47 ADE Hybrid */
.b47{background:linear-gradient(135deg,rgba(255,255,255,.96),rgba(227,242,255,.84));border:1px solid rgba(47,128,237,.16);border-radius:26px;padding:22px;box-shadow:0 12px 28px rgba(47,128,237,.08)}.b47-top{display:flex;justify-content:space-between;align-items:flex-end}.b47-title{font-size:24px;font-weight:950}.b47-tag{font-size:10px;font-weight:900;padding:5px 9px;border-radius:999px;background:#0b1f33;color:#fff}.b47-grid{display:grid;grid-template-columns:1.4fr repeat(4,1fr);gap:10px;margin-top:16px}.b47-hero{background:#0b1f33;color:#fff;border-radius:18px;padding:16px}.b47-hero .l{font-size:9px;opacity:.65}.b47-hero .v{font-size:34px;font-weight:950;margin-top:5px}.b47-mini{background:rgba(255,255,255,.8);border-radius:16px;padding:14px}.b47-mini .l{font-size:9px;color:#64748b}.b47-mini .v{font-size:20px;font-weight:850;margin-top:4px}

/* #48 Mobile Investment Feed */
.b48{background:#fff;border-radius:28px;padding:22px}.b48-title{font-size:24px;font-weight:950}.b48-tabs{display:flex;gap:8px;margin:14px 0}.b48-tab{padding:9px 13px;border-radius:999px;border:1px solid #d9dee5;font-size:12px;font-weight:750}.b48-tab.active{border:2px solid #111827}.b48-card{background:#fafafa;border-radius:18px;padding:18px;margin-top:12px}.b48-card .headline{font-size:18px;font-weight:900}.b48-card .body{font-size:14px;line-height:1.55;color:#4b5563;margin-top:10px}.b48-list{margin-top:12px}.b48-list .row{display:flex;justify-content:space-between;padding:10px 0;border-top:1px solid #eceff3}.b48-list .row .left{font-size:14px;font-weight:750}.b48-list .row .right{font-size:14px;font-weight:850;color:#e5484d}
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


def _metric_value(metrics: dict[str, Any], key: str) -> tuple[str, str, str]:
    metric = metrics.get(key)
    label = metric.label if metric else key.upper()
    value = "조회 실패" if metric is None or metric.value is None else f"{metric.value:,.2f}"
    delta = "-" if metric is None or metric.change_rate is None else f"{metric.change_rate:+.2f}%"
    return label, value, delta


def _render_43_reference(metrics: dict[str, Any], account: dict[str, Any] | None, positions: list[dict[str, Any]], important: list[dict[str, Any]]) -> None:
    k1 = _metric_value(metrics, "kospi")
    k2 = _metric_value(metrics, "kosdaq")
    total = float((account or {}).get("total_assets") or 0)
    cash = float((account or {}).get("cash") or 0)
    pnl = float((account or {}).get("pnl") or 0)
    pos = positions[0] if positions else {}
    pos_name = _text(pos, "name", "ticker") or "보유종목"
    pos_rate = _number(pos, "pnl_rate")
    event = important[0] if important else {}
    st.markdown('<div class="design-section-label">#43 Reference Replica · 사진 구성 최대 재현</div>', unsafe_allow_html=True)
    st.markdown(f'''<div class="ref-shell">
      <div class="ref-kpi-grid">
        <div class="ref-index"><div class="label">{k1[0]} · 실시간</div><div class="value">{k1[1]}</div><div class="delta">{k1[2]}</div><div class="ref-mini"></div></div>
        <div class="ref-index"><div class="label">{k2[0]} · 실시간</div><div class="value">{k2[1]}</div><div class="delta">{k2[2]}</div><div class="ref-mini"></div></div>
      </div>
      <div class="ref-card"><div class="ref-title">내 투자 현황</div><div class="ref-chip-row"><div class="ref-chip active">총자산 ₩{total:,.0f}</div><div class="ref-chip">예수금 ₩{cash:,.0f}</div><div class="ref-chip">손익 ₩{pnl:+,.0f}</div></div><div class="ref-soft"><b>{pos_name}</b><br><br>보유 포지션 수익률 <b>{pos_rate:+.2f}%</b></div></div>
      <div class="ref-card"><div class="ref-title">주요 이벤트</div><div class="ref-chip-row"><div class="ref-chip active">{str(event.get('일시(KST)') or '-')}</div><div class="ref-chip">{str(event.get('국가') or '-')}</div></div><div class="ref-soft">{str(event.get('이벤트') or event.get('구분') or '표시할 주요 이벤트가 없습니다.')}</div></div>
    </div>''', unsafe_allow_html=True)


def _render_44_brokerage(account: dict[str, Any] | None, positions: list[dict[str, Any]]) -> None:
    total = float((account or {}).get("total_assets") or 0)
    cash = float((account or {}).get("cash") or 0)
    evaluation = float((account or {}).get("evaluation_amount") or 0)
    pnl = float((account or {}).get("pnl") or 0)
    st.markdown('<div class="design-section-label">#44 Brokerage Clean · 증권사 계좌요약형</div>', unsafe_allow_html=True)
    html = f'<div class="b44"><h3>내 투자</h3><div class="b44-grid"><div class="b44-item"><div class="l">총자산</div><div class="v">₩{total:,.0f}</div></div><div class="b44-item"><div class="l">예수금</div><div class="v">₩{cash:,.0f}</div></div><div class="b44-item"><div class="l">평가금액</div><div class="v">₩{evaluation:,.0f}</div></div></div>'
    for row in positions[:3]:
        name = _text(row, "name", "ticker")
        ticker = _text(row, "ticker")
        price = _number(row, "current_price")
        rate = _number(row, "pnl_rate")
        html += f'<div class="b44-row"><div><div class="name">{name}</div><div class="meta">{ticker}</div></div><div class="right"><div class="price">₩{price:,.0f}</div><div class="rate">{rate:+.2f}%</div></div></div>'
    html += f'<div class="b44-row"><div class="name">평가손익</div><div class="right"><div class="price">₩{pnl:+,.0f}</div></div></div></div>'
    st.markdown(html, unsafe_allow_html=True)


def _render_45_editorial(important: list[dict[str, Any]]) -> None:
    st.markdown('<div class="design-section-label">#45 Editorial Cards · 이벤트 중심 편집형</div>', unsafe_allow_html=True)
    html = '<div class="b45"><div class="b45-head">오늘 시장에서<br>봐야 할 것</div><div class="b45-sub">중요 이벤트만 크게 읽는 구성</div><div class="b45-list">'
    for row in important[:4]:
        html += f'<div class="b45-line"><div class="time">{str(row.get("일시(KST)") or "-")}</div><div class="event">{str(row.get("이벤트") or row.get("구분") or "-")}</div><div class="badge">{str(row.get("중요도") or "-")}</div></div>'
    if not important:
        html += '<div class="b45-line"><div class="time">-</div><div class="event">표시할 주요 이벤트가 없습니다.</div><div class="badge">-</div></div>'
    html += '</div></div>'
    st.markdown(html, unsafe_allow_html=True)


def _render_46_dense(metrics: dict[str, Any]) -> None:
    st.markdown('<div class="design-section-label">#46 Data Dense · 고밀도 터미널형</div>', unsafe_allow_html=True)
    ordered = ["kospi", "kosdaq", "sp500", "nasdaq", "usdkrw", "vix"]
    cells = []
    for key in ordered:
        label, value, delta = _metric_value(metrics, key)
        cells.append(f'<div class="b46-cell"><div class="l">{label}</div><div class="v">{value}</div><div class="d">{delta}</div></div>')
    st.markdown('<div class="b46"><div class="b46-title">ADE / MARKET SNAPSHOT</div><div class="b46-grid">'+''.join(cells)+'</div></div>', unsafe_allow_html=True)


def _render_47_hybrid(account: dict[str, Any] | None) -> None:
    total = float((account or {}).get("total_assets") or 0)
    cash = float((account or {}).get("cash") or 0)
    evaluation = float((account or {}).get("evaluation_amount") or 0)
    pnl = float((account or {}).get("pnl") or 0)
    count = int((account or {}).get("position_count") or 0)
    st.markdown('<div class="design-section-label">#47 ADE Hybrid · 사진 구조 + ADE 전문형</div>', unsafe_allow_html=True)
    st.markdown(f'''<div class="b47"><div class="b47-top"><div class="b47-title">Portfolio Command</div><div class="b47-tag">ADE</div></div><div class="b47-grid"><div class="b47-hero"><div class="l">총자산</div><div class="v">₩{total:,.0f}</div></div><div class="b47-mini"><div class="l">예수금</div><div class="v">₩{cash:,.0f}</div></div><div class="b47-mini"><div class="l">평가금액</div><div class="v">₩{evaluation:,.0f}</div></div><div class="b47-mini"><div class="l">평가손익</div><div class="v">₩{pnl:+,.0f}</div></div><div class="b47-mini"><div class="l">보유종목</div><div class="v">{count}개</div></div></div></div>''', unsafe_allow_html=True)


def _render_48_feed(positions: list[dict[str, Any]], sectors: list[dict[str, Any]]) -> None:
    st.markdown('<div class="design-section-label">#48 Mobile Investment Feed · 모바일 발견형</div>', unsafe_allow_html=True)
    html = '<div class="b48"><div class="b48-title">발견</div><div class="b48-tabs"><div class="b48-tab active">보유종목</div><div class="b48-tab">시장</div><div class="b48-tab">업종</div></div><div class="b48-card">'
    if positions:
        row = positions[0]
        html += f'<div class="headline">{_text(row,"name","ticker")}</div><div class="body">현재가 ₩{_number(row,"current_price"):,.0f} · 수익률 {_number(row,"pnl_rate"):+.2f}%</div>'
    else:
        html += '<div class="headline">보유종목 없음</div><div class="body">계좌에 보유 중인 종목이 없습니다.</div>'
    html += '<div class="b48-list">'
    for row in sectors[:3]:
        html += f'<div class="row"><div class="left">{str(row.get("sector") or "-")}</div><div class="right">{_number(row,"change_rate"):+.2f}%</div></div>'
    html += '</div></div></div>'
    st.markdown(html, unsafe_allow_html=True)


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
    st.divider()
    if st.button("주문 화면으로", type="primary", use_container_width=True, key=f"portfolio_order_{ticker}"):
        st.session_state.ade_order_ticker = ticker
        st.session_state.ade_order_symbol = name
        st.session_state.ade_primary_page = "주문"
        base_app._reset_order_confirmation()
        st.rerun()


def render_overview_workspace(base_app: Any) -> None:
    st.markdown(_STICKY_KPI_STYLE, unsafe_allow_html=True)
    st.markdown("### 상황종합판 · UI TEST 43–48")
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

    _render_43_reference(metrics, account, positions, important)
    _render_44_brokerage(account, positions)
    _render_45_editorial(important)
    _render_46_dense(metrics)
    _render_47_hybrid(account)
    _render_48_feed(positions, sectors)

    st.markdown("### 보유종목 선택")
    for row in positions:
        ticker = _text(row, "ticker")
        name = _text(row, "name", "ticker")
        if st.button(f"{name} · {ticker}", key=f"ui_test_holding_{ticker}", use_container_width=True):
            st.session_state.ade_portfolio_ticker = ticker
            st.rerun()

    with st.expander("향후 90일 전체 일정", expanded=False):
        if rows:
            frame = pd.DataFrame(rows)
            st.dataframe(frame, hide_index=True, use_container_width=True)
        else:
            st.info("표시할 전체 이벤트가 없습니다.")

    for warning in warnings:
        st.caption(str(warning))
