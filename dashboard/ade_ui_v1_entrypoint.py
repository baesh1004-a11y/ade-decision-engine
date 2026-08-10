from __future__ import annotations

from dashboard import ade_ui_v1_app as base_app
from dashboard.overview_workspace import render_overview_workspace
from dashboard.standard_order_panel import (
    OrderContext,
    render_order_ticket,
    render_scheduled_order_tab,
    render_search_launcher,
)


_RECOMMENDATION_STYLE = """
<style>
.ade-reco-shell{background:linear-gradient(180deg,#dff5f3 0%,#eef8ef 48%,#f4f6f8 100%);padding:16px;border-radius:30px}
.ade-reco-hero{background:#fff;border-radius:28px;padding:24px;margin:12px 0;box-shadow:0 4px 14px rgba(22,47,66,.04)}
.ade-reco-title{font-size:30px;font-weight:950;letter-spacing:-.045em;color:#0b0f14}.ade-reco-meta{font-size:12px;color:#7b8794;margin-top:6px}
.ade-chip-row{display:flex;gap:10px;overflow-x:auto;margin-top:18px;padding-bottom:2px}.ade-chip{white-space:nowrap;border:1px solid #d8dee6;border-radius:999px;padding:9px 14px;font-size:13px;font-weight:800;background:#fff;color:#4b5563}.ade-chip.active{border:2px solid #111827;color:#111827}.ade-chip .up{color:#e5484d}.ade-chip .down{color:#2563eb}
.ade-reco-soft{background:#fafafa;border-radius:18px;padding:20px;margin-top:18px}.ade-reco-soft-title{font-size:18px;font-weight:900}.ade-reco-soft-body{font-size:14px;line-height:1.55;color:#4b5563;margin-top:10px}
.ade-reco-kpis{display:grid;grid-template-columns:1.35fr 1fr 1fr;gap:12px;margin-top:18px}.ade-reco-kpi{background:#fafafa;border-radius:18px;padding:16px;border:1px solid rgba(15,23,42,.06)}.ade-reco-kpi.hero{background:linear-gradient(135deg,#e7f4ff,#e4f7ef);border:1px solid rgba(47,128,237,.13)}.ade-reco-kpi .l{font-size:12px;font-weight:800;color:#6f7b88}.ade-reco-kpi .v{font-size:28px;font-weight:950;letter-spacing:-.04em;margin-top:5px;color:#111827}.ade-reco-kpi.hero .v{font-size:36px;color:#12314d}
.ade-reco-section{background:#fff;border-radius:28px;padding:24px;margin:14px 0;box-shadow:0 4px 14px rgba(22,47,66,.04)}.ade-reco-section-title{font-size:25px;font-weight:950;letter-spacing:-.04em;color:#0b0f14}.ade-reco-section-sub{font-size:12px;color:#8a94a1;margin-top:5px}
.ade-replay-summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-top:16px}.ade-replay-box{background:#fafafa;border-radius:16px;padding:14px;border:1px solid rgba(15,23,42,.06)}.ade-replay-box .l{font-size:10px;font-weight:800;color:#7b8794}.ade-replay-box .v{font-size:22px;font-weight:950;margin-top:5px}.ade-replay-box.success .v{color:#e5484d}.ade-replay-box.fail .v{color:#2563eb}.ade-replay-box.neutral .v{color:#6b7280}
.ade-reco-pill-row{display:flex;gap:9px;flex-wrap:wrap;margin-top:14px}.ade-reco-pill{padding:8px 12px;border-radius:999px;border:1px solid #dbe1e7;background:#fff;font-size:12px;font-weight:800}.ade-reco-pill.active{border:2px solid #111827}
.ade-evidence-list{margin-top:14px}.ade-evidence-row{display:grid;grid-template-columns:34px 150px 1fr;gap:14px;align-items:start;padding:15px 0;border-top:1px solid #eceff3}.ade-evidence-row:first-child{border-top:0}.ade-evidence-no{width:28px;height:28px;border-radius:999px;background:#101922;color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:900}.ade-evidence-label{font-size:14px;font-weight:900}.ade-evidence-body{font-size:14px;line-height:1.45;color:#374151}
.ade-news-list{margin-top:14px}.ade-news-row{display:grid;grid-template-columns:1fr auto;gap:14px;padding:14px 0;border-top:1px solid #eceff3}.ade-news-row:first-child{border-top:0}.ade-news-title{font-size:15px;font-weight:800;line-height:1.4}.ade-news-meta{font-size:10px;color:#9aa3ad;margin-top:4px}.ade-news-source{font-size:11px;color:#7b8794;white-space:nowrap}
@media(max-width:900px){.ade-reco-kpis{grid-template-columns:1fr}.ade-replay-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.ade-evidence-row{grid-template-columns:30px 1fr}.ade-evidence-label{grid-column:2}.ade-evidence-body{grid-column:2}}
</style>
"""


def _render_overview() -> None:
    render_overview_workspace(base_app)


def _render_status_bar() -> None:
    import time
    import streamlit as st

    from broker.kis_websocket import shared_market_client
    from dashboard.kis_zero_base_bridge import kis_configured, kis_paper_enabled
    from dashboard.order_candidate_store import store_health

    if kis_paper_enabled():
        kis_text, kis_class = "KIS PAPER", "ade-ok"
    elif kis_configured():
        kis_text, kis_class = "KIS CHECK", ""
    else:
        kis_text, kis_class = "KIS OFF", ""

    health = shared_market_client().health_snapshot()
    latest_received_at = health.get("latest_received_at")
    if health.get("connected") and latest_received_at:
        age = time.time() - float(latest_received_at)
        ws_text = "LIVE" if age <= 3 else ("LIVE DELAY" if age <= 10 else "LIVE STALE")
        ws_class = "ade-ok" if age <= 3 else ""
    elif health.get("connected"):
        ws_text, ws_class = "LIVE WAIT", ""
    else:
        ws_text, ws_class = "LIVE OFF", ""

    candidate_health = store_health()
    schema_version = candidate_health.get("schema_version")
    candidate_text = f"DB v{schema_version}" if candidate_health.get("status") == "정상" else "DB ERROR"
    candidate_class = "ade-ok" if candidate_health.get("status") == "정상" else ""
    st.markdown(
        f'<div class="ade-statusbar"><span>ADE TERMINAL</span><span class="{kis_class}">{kis_text}</span><span class="{ws_class}">{ws_text}</span><span class="{candidate_class}">{candidate_text}</span><span>REPLAY / STO READY</span></div>',
        unsafe_allow_html=True,
    )


def _open_order(ticker: str, symbol: str) -> None:
    import streamlit as st

    st.session_state.ade_order_ticker = ticker
    st.session_state.ade_order_symbol = symbol
    base_app._reset_order_confirmation()
    st.rerun()


def _save_candidate(market: str, ticker: str, symbol: str) -> None:
    import streamlit as st

    try:
        base_app._add_order_candidate(market, ticker, symbol)
        st.success(f"{symbol}을 주문후보에 저장했습니다.")
    except Exception as exc:
        st.error(str(exc))


def _submit_order(ticker: str, side: str, quantity: int, order_type: str, limit_price: float | None) -> tuple[bool, str]:
    try:
        result = base_app.submit_paper_order(
            ticker=ticker,
            side="BUY" if side == "매수" else "SELL",
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )
        if result.accepted:
            base_app.refresh_order_views()
            return True, f"접수 완료 · 주문번호 {result.order_id or '-'}"
        return False, "주문이 거절되었습니다."
    except Exception as exc:
        base_app.LOGGER.exception("Standard order submit failed ticker=%s", ticker)
        return False, f"주문 전송 실패: {exc}"


def _render_standard_order_ticket(market: str, ticker: str) -> None:
    import streamlit as st

    if st.button("← 주문목록으로 돌아가기", key="standard_order_back"):
        st.session_state.ade_order_ticker = None
        st.rerun()

    account, positions, account_error = base_app._cached_kis_snapshot() if market == "kr" else (None, [], None)
    quote, quote_error = base_app.load_kis_quote(ticker) if market == "kr" else (None, None)
    holding = next((row for row in positions if str(row.get("ticker")) == str(ticker)), None)
    name = str((holding or {}).get("name") or st.session_state.get("ade_order_symbol") or ticker)
    current_price = float((quote or {}).get("price") or (holding or {}).get("current_price") or 0)
    change_rate = float((quote or {}).get("change_rate") or 0)
    cash = float((account or {}).get("cash") or 0)
    orderable, orderable_error = base_app.load_orderable(ticker, current_price, "LIMIT") if market == "kr" else (None, None)
    orderable_quantity = int((orderable or {}).get("orderable_quantity") or 0)
    holding_quantity = int((holding or {}).get("quantity") or 0)

    context = OrderContext(
        market=market,
        ticker=ticker,
        name=name,
        current_price=current_price,
        change_rate=change_rate,
        cash=cash,
        holding_quantity=holding_quantity,
        orderable_quantity=orderable_quantity,
    )

    current = st.session_state.get("ade_order_ticket_tab", "일반주문")
    if current not in {"일반주문", "예약주문"}:
        current = "일반주문"
    selected = st.segmented_control(
        "주문 방식",
        options=["일반주문", "예약주문"],
        default=current,
        key=f"ade_order_ticket_segment_{market}_{ticker}",
        label_visibility="collapsed",
    )
    st.session_state.ade_order_ticket_tab = selected or current

    if st.session_state.ade_order_ticket_tab == "예약주문":
        render_scheduled_order_tab(
            market=market,
            ticker=ticker,
            name=name,
            current_price=current_price,
        )
    else:
        render_order_ticket(context=context, submit_callback=_submit_order)
        details = [message for message in [account_error, quote_error, orderable_error] if message]
        if details:
            st.caption(" · ".join(details))


def _render_orders() -> None:
    import streamlit as st

    base_app._render_order_flash()
    previous_market = st.session_state.ade_market
    market = base_app._market_selector("ade_order_market")
    if previous_market != market:
        base_app._release_live_lease()
        st.session_state.ade_order_ticker = None
        base_app._reset_order_confirmation()
        base_app._clear_live_session_state()
    st.session_state.ade_market = market

    if st.session_state.ade_order_ticker:
        _render_standard_order_ticket(market, str(st.session_state.ade_order_ticker))
        return

    st.markdown("### 주문 데스크")
    st.caption("종목 탐색 → 주문 판단 → 주문/체결 관리")
    render_search_launcher(
        market=market,
        search_func=base_app._search_order_symbols,
        on_open=_open_order,
        on_add_candidate=lambda ticker, symbol: _save_candidate(market, ticker, symbol),
    )

    options = ["주문후보", "보유종목", "미체결", "당일 체결", "예약주문"]
    current = st.session_state.get("ade_order_tab", "주문후보")
    if current not in options:
        current = "주문후보"
    selected = st.segmented_control(
        "주문 데스크 하위 메뉴",
        options=options,
        default=current,
        key=f"ade_order_segment_{market}",
        label_visibility="collapsed",
    )
    st.session_state.ade_order_tab = selected or current
    active = st.session_state.ade_order_tab

    if active == "주문후보":
        base_app._render_candidate_controls(market)
    elif active == "보유종목":
        account, positions, error = base_app._cached_kis_snapshot() if market == "kr" else (None, [], None)
        if not positions:
            st.info("보유종목이 없습니다.")
        for row in positions:
            if st.button(
                f"{row.get('name') or row.get('ticker')} · {row.get('ticker')} · {int(row.get('quantity') or 0)}주",
                key=f"standard_holding_{row.get('ticker')}",
                use_container_width=True,
            ):
                _open_order(str(row.get("ticker")), str(row.get("name") or row.get("ticker")))
        if account:
            st.caption(f"KIS 예수금 ₩{float(account.get('cash') or 0):,.0f}")
        if error:
            st.caption(error)
    elif active == "미체결":
        base_app._render_pending_orders()
    elif active == "당일 체결":
        base_app._render_daily_orders()
    else:
        render_scheduled_order_tab(market=market)


def _render_recommendation_reason(payload: dict, selected: dict) -> str:
    reason = (
        payload.get("recommendation_reason")
        or payload.get("reason")
        or payload.get("rationale")
        or selected.get("recommendation_reason")
        or selected.get("reason")
    )
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    if isinstance(reason, (list, tuple)) and reason:
        return " · ".join(str(item) for item in reason[:5])
    weekly = float(selected.get("weekly_similarity") or selected.get("score") or selected.get("final_similarity") or 0)
    sto = float(selected.get("sto_similarity") or 0)
    replay_matches = payload.get("replay_matches") or []
    replay_count = len(replay_matches) if isinstance(replay_matches, list) else 0
    return f"저장된 추천근거 원문 없음 · 주봉 유사도 {weekly:.2f}% · STO 유사도 {sto:.2f}% · Replay {replay_count}건"


def _classify_replay(match: dict) -> str:
    def num(*keys):
        for key in keys:
            try:
                value = match.get(key)
                if value not in (None, ""):
                    return float(value)
            except (TypeError, ValueError):
                pass
        return None
    final_return = num("final_return", "return_20d", "future_return")
    max_return = num("max_return")
    max_drawdown = num("max_drawdown")
    if final_return is not None:
        if final_return >= 5:
            return "success"
        if final_return <= -5:
            return "fail"
    if max_return is not None and max_return >= 10 and (max_drawdown is None or max_drawdown > -10):
        return "success"
    if max_drawdown is not None and max_drawdown <= -10:
        return "fail"
    return "neutral"


def _replay_summary(matches: list[dict]) -> tuple[int, int, int, str, str]:
    success = sum(_classify_replay(item) == "success" for item in matches)
    neutral = sum(_classify_replay(item) == "neutral" for item in matches)
    fail = sum(_classify_replay(item) == "fail" for item in matches)
    max_returns = []
    drawdowns = []
    for item in matches:
        try:
            if item.get("max_return") not in (None, ""):
                max_returns.append(float(item.get("max_return")))
        except (TypeError, ValueError):
            pass
        try:
            if item.get("max_drawdown") not in (None, ""):
                drawdowns.append(float(item.get("max_drawdown")))
        except (TypeError, ValueError):
            pass
    avg_max = f"{sum(max_returns)/len(max_returns):+.2f}%" if max_returns else "-"
    avg_dd = f"{sum(drawdowns)/len(drawdowns):+.2f}%" if drawdowns else "-"
    return success, neutral, fail, avg_max, avg_dd


def _render_recommendation_detail(market: str, ticker: str) -> None:
    import streamlit as st

    st.markdown(_RECOMMENDATION_STYLE, unsafe_allow_html=True)

    if st.button("← 추천종목으로 돌아가기", key=f"terminal_reco_back_{market}_{ticker}"):
        st.session_state.ade_recommendation_detail = None
        st.session_state.ade_show_heavy_charts = False
        st.rerun()

    recommendations, context = base_app._load_recommendations(market)
    selected = next((row for row in recommendations if str(row.get("ticker")) == str(ticker)), None)
    if selected is None:
        st.warning("선택 종목을 찾을 수 없습니다.")
        return

    profile = base_app.get_market_profile(market)
    normalized_ticker = base_app.normalize_ticker(ticker, market)
    payload = base_app._safe_json(selected.get("payload_json"))
    run_id = context.run_id if context else "-"
    symbol = str(selected.get("symbol") or selected.get("name") or ticker)
    weekly = float(selected.get("weekly_similarity") or selected.get("score") or selected.get("final_similarity") or 0)
    sto = float(selected.get("sto_similarity") or 0)
    replay_matches = [item for item in (payload.get("replay_matches") or []) if isinstance(item, dict)]
    replay_count = len(replay_matches)
    prediction = payload.get("prediction") if isinstance(payload.get("prediction"), dict) else {}
    success, neutral, fail, avg_max, avg_dd = _replay_summary(replay_matches)

    with base_app.sqlite3.connect(str(profile.db_path), timeout=5) as conn:
        conn.row_factory = base_app.sqlite3.Row
        current, current_source, current_warning = base_app._load_current_bars_resilient(conn, market, normalized_ticker, profile.price_source)

    reason_text = _render_recommendation_reason(payload, selected)
    prediction_chip = ""
    if prediction:
        grade = str(prediction.get("grade") or "-")
        prediction_chip = f'<div class="ade-chip">Prediction {grade}</div>'

    st.markdown('<div class="ade-reco-shell">', unsafe_allow_html=True)
    st.markdown(
        f'''<div class="ade-reco-hero"><div class="ade-reco-title">{symbol}</div><div class="ade-reco-meta">{ticker} · 실행ID {run_id} · 가격소스 {current_source}</div><div class="ade-chip-row"><div class="ade-chip active">추천점수 {weekly:.1f}</div><div class="ade-chip">STO {sto:.1f}%</div><div class="ade-chip">Replay {replay_count}건</div>{prediction_chip}</div><div class="ade-reco-soft"><div class="ade-reco-soft-title">왜 이 종목인가</div><div class="ade-reco-soft-body">{reason_text}</div></div><div class="ade-reco-kpis"><div class="ade-reco-kpi hero"><div class="l">추천점수</div><div class="v">{weekly:.1f}</div></div><div class="ade-reco-kpi"><div class="l">STO 유사도</div><div class="v">{sto:.1f}%</div></div><div class="ade-reco-kpi"><div class="l">Replay 사례</div><div class="v">{replay_count}건</div></div></div></div>''',
        unsafe_allow_html=True,
    )
    if current_warning:
        st.caption(current_warning)

    st.markdown(
        f'''<div class="ade-reco-section"><div class="ade-reco-section-title">Replay 결과 요약</div><div class="ade-reco-section-sub">단순 사례 수보다 과거 결과 분포와 손익 폭을 먼저 확인합니다.</div><div class="ade-replay-summary"><div class="ade-replay-box success"><div class="l">성공</div><div class="v">{success}</div></div><div class="ade-replay-box neutral"><div class="l">중립</div><div class="v">{neutral}</div></div><div class="ade-replay-box fail"><div class="l">실패</div><div class="v">{fail}</div></div><div class="ade-replay-box"><div class="l">평균 최대수익</div><div class="v">{avg_max}</div></div><div class="ade-replay-box"><div class="l">평균 최대낙폭</div><div class="v">{avg_dd}</div></div></div></div>''',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="ade-reco-section"><div class="ade-reco-section-title">현재 ↔ 과거 유사사례 직접 비교</div><div class="ade-reco-section-sub">현재 패턴과 Replay 사례를 같은 검증 작업공간에서 비교합니다.</div><div class="ade-reco-pill-row"><div class="ade-reco-pill active">현재</div><div class="ade-reco-pill">과거 사례</div><div class="ade-reco-pill">Overlay</div><div class="ade-reco-pill">STO</div><div class="ade-reco-pill">미래경로</div></div></div>', unsafe_allow_html=True)
    base_app.render_recommendation_detail_enhancements(
        db_path=str(profile.db_path),
        payload=payload,
        selected=selected,
        market=market,
        ticker=normalized_ticker,
        current=current,
        current_label=symbol,
        include_heavy=True,
    )

    supply = base_app.load_supply_demand_health(normalized_ticker, market=market)
    supply_text = str((supply.get("investor") or {}).get("detail") or "수급 확인 필요")
    cautions = payload.get("risk_factors") or payload.get("cautions") or payload.get("warnings") or []
    if isinstance(cautions, str):
        cautions = [cautions]
    caution_text = " · ".join(str(item) for item in cautions[:5]) if cautions else "저장된 반대 근거 없음 · 데이터 부재를 긍정 신호로 해석하지 않음"

    st.markdown(
        f'''<div class="ade-reco-section"><div class="ade-reco-section-title">판단 근거</div><div class="ade-reco-section-sub">사진의 카드형 정보 위계를 적용해 한 항목씩 읽도록 정리했습니다.</div><div class="ade-evidence-list"><div class="ade-evidence-row"><div class="ade-evidence-no">1</div><div class="ade-evidence-label">알고리즘 근거</div><div class="ade-evidence-body">{reason_text}</div></div><div class="ade-evidence-row"><div class="ade-evidence-no">2</div><div class="ade-evidence-label">Replay 결과</div><div class="ade-evidence-body">성공 {success} · 중립 {neutral} · 실패 {fail} · 평균 최대수익 {avg_max} · 평균 최대낙폭 {avg_dd}</div></div><div class="ade-evidence-row"><div class="ade-evidence-no">3</div><div class="ade-evidence-label">환경·수급</div><div class="ade-evidence-body">{supply_text}</div></div><div class="ade-evidence-row"><div class="ade-evidence-no">4</div><div class="ade-evidence-label">반대 근거</div><div class="ade-evidence-body">{caution_text}</div></div></div></div>''',
        unsafe_allow_html=True,
    )

    news_rows, news_warning = base_app._cached_security_news(ticker, symbol, 8)
    st.markdown('<div class="ade-reco-section"><div class="ade-reco-section-title">뉴스·공시</div><div class="ade-reco-section-sub">최신 이슈를 카드형 목록으로 확인합니다.</div><div class="ade-news-list">', unsafe_allow_html=True)
    if news_rows:
        for row in list(news_rows)[:8]:
            if isinstance(row, dict):
                title = str(row.get("title") or row.get("제목") or row.get("headline") or "-")
                source = str(row.get("source") or row.get("출처") or "")
                when = str(row.get("published_at") or row.get("date") or row.get("일시") or "")
                st.markdown(f'<div class="ade-news-row"><div><div class="ade-news-title">{title}</div><div class="ade-news-meta">{when}</div></div><div class="ade-news-source">{source}</div></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="ade-news-row"><div class="ade-news-title">{str(row)}</div><div></div></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="padding:16px 0;color:#8a94a1">표시할 최신 뉴스·공시가 없습니다.</div>', unsafe_allow_html=True)
    if news_warning:
        st.caption(news_warning)
    st.markdown('</div></div>', unsafe_allow_html=True)

    if st.button("검증 후 주문 화면으로", type="primary", use_container_width=True, key=f"verified_order_{market}_{ticker}"):
        try:
            base_app._add_order_candidate(market, ticker, symbol)
        except Exception:
            pass
        st.session_state.ade_order_ticker = ticker
        base_app._navigate_primary("주문")
    st.markdown('</div>', unsafe_allow_html=True)


def run() -> None:
    base_app._render_overview = _render_overview
    base_app._render_status_bar = _render_status_bar
    base_app._render_orders = _render_orders
    base_app._render_recommendation_detail = _render_recommendation_detail
    base_app.run()


if __name__ == "__main__":
    run()
