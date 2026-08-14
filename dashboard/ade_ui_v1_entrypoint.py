from __future__ import annotations

from dashboard import ade_ui_v1_app as base_app
from dashboard.overview_workspace import render_overview_workspace
from dashboard.standard_order_panel import (
    OrderContext,
    render_order_ticket,
    render_scheduled_order_tab,
    render_search_launcher,
)
from maintenance.recommendation_runner import get_status, start_job


_RECOMMENDATION_STYLE = """
<style>
.ade-reco-shell{background:linear-gradient(180deg,#dff5f3 0%,#eef8ef 48%,#f4f6f8 100%);padding:16px;border-radius:30px}
.ade-reco-list-shell{background:linear-gradient(180deg,#dff5f3 0%,#edf8f1 55%,#f4f6f8 100%);padding:16px;border-radius:30px}
.ade-reco-list-head{background:#fff;border-radius:28px;padding:24px;margin:10px 0 14px;box-shadow:0 4px 14px rgba(22,47,66,.04)}
.ade-reco-list-title{font-size:30px;font-weight:950;letter-spacing:-.045em;color:#0b0f14}.ade-reco-list-sub{font-size:12px;color:#7b8794;margin-top:6px}
.ade-reco-list-card{background:#fff;border-radius:26px;padding:20px 22px;margin:12px 0;border:1px solid rgba(15,23,42,.06);box-shadow:0 4px 14px rgba(22,47,66,.035)}
.ade-reco-list-top{display:grid;grid-template-columns:54px 1.7fr .9fr .9fr .9fr;gap:12px;align-items:center}
.ade-reco-rank{width:42px;height:42px;border-radius:14px;background:#eef6ff;color:#12314d;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:950}
.ade-reco-name{font-size:20px;font-weight:950;letter-spacing:-.03em;color:#111827}.ade-reco-code{font-size:11px;color:#8a94a1;margin-top:3px}
.ade-reco-stat .l{font-size:10px;color:#8a94a1;font-weight:800}.ade-reco-stat .v{font-size:20px;font-weight:950;color:#111827;margin-top:3px}
.ade-reco-stat.good .v{color:#e5484d}.ade-reco-stat.bad .v{color:#2563eb}.ade-reco-stat.neutral .v{color:#6b7280}
.ade-reco-reason{background:#fafafa;border-radius:16px;padding:14px 16px;margin-top:14px;font-size:13px;line-height:1.5;color:#4b5563}
.ade-reco-result-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.ade-reco-result-chip{padding:6px 9px;border-radius:999px;font-size:11px;font-weight:850;border:1px solid #dbe1e7;background:#fff}.ade-reco-result-chip.success{background:#fff1f2;color:#b4232f;border-color:#f8c9ce}.ade-reco-result-chip.neutral{background:#f4f6f8;color:#697586}.ade-reco-result-chip.fail{background:#eef4ff;color:#2459a8;border-color:#cdddf8}
.ade-reco-actions{display:grid;grid-template-columns:1fr auto;gap:10px;margin-top:12px}
.ade-reco-run-card{background:#fff;border-radius:24px;padding:20px;margin:0 0 16px;border:1px solid rgba(15,23,42,.06);box-shadow:0 4px 14px rgba(22,47,66,.035)}
.ade-reco-run-top{display:grid;grid-template-columns:1.5fr auto;gap:18px;align-items:start}.ade-reco-run-title{font-size:21px;font-weight:950;letter-spacing:-.03em;color:#111827}.ade-reco-run-meta{font-size:11px;color:#8a94a1;margin-top:5px}.ade-reco-run-stage{display:inline-flex;align-items:center;padding:7px 10px;border-radius:999px;background:#eef6ff;color:#24415e;font-size:11px;font-weight:900}.ade-reco-run-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:16px}.ade-reco-run-box{background:#f8fafc;border-radius:16px;padding:13px 14px;border:1px solid #eef1f4}.ade-reco-run-box .l{font-size:9px;color:#8b96a3;font-weight:850}.ade-reco-run-box .v{font-size:17px;color:#111827;font-weight:950;margin-top:4px}.ade-reco-run-note{font-size:11px;color:#7b8794;margin-top:12px}.ade-reco-run-progress{margin-top:14px}.ade-reco-run-progress-head{display:flex;justify-content:space-between;gap:10px;font-size:12px;font-weight:850;color:#44546a}.ade-reco-run-progress-bar{height:8px;border-radius:999px;background:#e9eef3;overflow:hidden;margin-top:8px}.ade-reco-run-progress-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,#5ca9ff,#62c9a5)}.ade-reco-run-progress-sub{font-size:10px;color:#8a94a1;margin-top:7px}
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
@media(max-width:900px){.ade-reco-list-top{grid-template-columns:48px 1fr 1fr}.ade-reco-list-top .optional{display:none}.ade-reco-kpis{grid-template-columns:1fr}.ade-replay-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.ade-evidence-row{grid-template-columns:30px 1fr}.ade-evidence-label{grid-column:2}.ade-evidence-body{grid-column:2}.ade-reco-run-top{grid-template-columns:1fr}.ade-reco-run-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}
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


def _format_seconds(value: object) -> str:
    try:
        seconds = max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return "-"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}시간 {minutes:02d}분 {seconds:02d}초"
    if minutes:
        return f"{minutes}분 {seconds:02d}초"
    return f"{seconds}초"


def _render_recommendation_generation(market: str, context) -> None:
    import streamlit as st

    profile = base_app.get_market_profile(market)
    runtime = get_status(profile.code)
    running = bool(runtime.get("running"))
    last_run = str(context.finished_at or "-")[:19] if context is not None else "없음"
    last_count = int(context.recommendation_count or 0) if context is not None else 0
    elapsed = _format_seconds(runtime.get("elapsed_seconds")) if runtime.get("elapsed_seconds") is not None else "-"
    overall = float(runtime.get("overall_progress", runtime.get("progress", 0.0)) or 0.0)
    current = int(runtime.get("current") or 0)
    total = int(runtime.get("total") or 0)
    remaining = int(runtime.get("remaining_symbols") or max(0, total - current)) if total else 0
    stage = str(runtime.get("stage_label") or ("실행 중" if running else "대기"))
    current_ticker = str(runtime.get("current_ticker") or "-")
    percent = min(100.0, max(0.0, overall * 100.0))

    st.markdown(
        f'''<div class="ade-reco-run-card"><div class="ade-reco-run-top"><div><div class="ade-reco-run-title">추천 다시 계산</div><div class="ade-reco-run-meta">최근 완료 {last_run} · 저장 추천 {last_count}개</div></div><div class="ade-reco-run-stage">{stage}</div></div><div class="ade-reco-run-summary"><div class="ade-reco-run-box"><div class="l">기본 기간</div><div class="v">2년</div></div><div class="ade-reco-run-box"><div class="l">패턴 풀</div><div class="v">100</div></div><div class="ade-reco-run-box"><div class="l">주봉 / STO</div><div class="v">85 / 85</div></div><div class="ade-reco-run-box"><div class="l">추천 수</div><div class="v">20</div></div></div>''',
        unsafe_allow_html=True,
    )

    if running:
        progress_detail = f"{current:,}/{total:,}" if total else "초기화 중"
        st.markdown(
            f'''<div class="ade-reco-run-progress"><div class="ade-reco-run-progress-head"><span>{stage}</span><span>{percent:.0f}%</span></div><div class="ade-reco-run-progress-bar"><div class="ade-reco-run-progress-fill" style="width:{percent:.1f}%"></div></div><div class="ade-reco-run-progress-sub">경과 {elapsed} · 처리 {progress_detail} · 남음 {remaining:,} · 현재 {current_ticker}</div></div><div class="ade-reco-run-note">화면은 가볍게 유지하고 계산은 백그라운드에서 계속 진행됩니다.</div></div>''',
            unsafe_allow_html=True,
        )
        st.caption("진행 상황은 새로고침할 때 갱신됩니다. 계산 자체는 화면 새로고침과 무관하게 계속됩니다.")
        return

    state = str(runtime.get("state") or "IDLE")
    if state == "COMPLETED" and runtime.get("elapsed_seconds") is not None:
        st.markdown(f'<div class="ade-reco-run-note">최근 수동 계산 소요시간 {_format_seconds(runtime.get("elapsed_seconds"))}</div>', unsafe_allow_html=True)
    elif state == "FAILED" and runtime.get("error_message"):
        st.markdown(f'<div class="ade-reco-run-note">최근 계산 실패 · {str(runtime.get("error_message"))}</div>', unsafe_allow_html=True)

    st.markdown('<div class="ade-reco-run-note">기본값으로 바로 실행할 수 있습니다. 세부 조건을 바꿀 때만 계산 설정을 펼치세요.</div></div>', unsafe_allow_html=True)
    if st.button("추천 다시 계산", type="primary", use_container_width=True, key=f"ade_recalc_start_{market}"):
        request_id = start_job(
            profile.code,
            profile.db_path,
            top_n=int(st.session_state.get(f"ade_recalc_{market}_top", 20)),
            weekly_pool_n=int(st.session_state.get(f"ade_recalc_{market}_pool", 100)),
            candidate_years=int(st.session_state.get(f"ade_recalc_{market}_years", 2)),
            use_recent_replay=True,
            use_weekly_filter=True,
            min_weekly_similarity=float(st.session_state.get(f"ade_recalc_{market}_weekly", 85.0)),
            use_sto_filter=True,
            min_sto_similarity=float(st.session_state.get(f"ade_recalc_{market}_sto", 85.0)),
        )
        if request_id:
            st.success("추천 계산을 시작했습니다. 아래 진행 카드에서 상태를 확인할 수 있습니다.")
            st.rerun()
        else:
            st.warning("이미 같은 시장의 추천 계산이 실행 중입니다.")

    with st.expander("계산 설정", expanded=False):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.number_input("과거 기간(년)", min_value=1, max_value=10, value=2, key=f"ade_recalc_{market}_years")
        c2.number_input("과거 패턴 수", min_value=10, max_value=1000, value=100, step=10, key=f"ade_recalc_{market}_pool")
        c3.number_input("최소 주봉", min_value=0.0, max_value=100.0, value=85.0, step=1.0, key=f"ade_recalc_{market}_weekly")
        c4.number_input("STO 통과", min_value=0.0, max_value=100.0, value=85.0, step=1.0, key=f"ade_recalc_{market}_sto")
        c5.number_input("추천 수", min_value=1, max_value=50, value=20, key=f"ade_recalc_{market}_top")
        st.caption("추천 순위는 주봉 유사도를 기준으로 하고 STO는 통과 필터로 사용합니다.")


def _render_recommendations() -> None:
    import streamlit as st

    st.markdown(_RECOMMENDATION_STYLE, unsafe_allow_html=True)
    market = base_app._market_selector("ade_reco_market")
    if st.session_state.ade_recommendation_detail:
        _render_recommendation_detail(market, st.session_state.ade_recommendation_detail)
        return

    recommendations, context = base_app._load_recommendations(market)
    title = "국내 추천종목" if market == "kr" else "미국 추천종목"
    meta = ""
    if context is not None:
        meta = f"실행ID {context.run_id} · 생성 {str(context.finished_at or '-')[:19]} · 추천 {context.recommendation_count}개"
    st.markdown(f'<div class="ade-reco-list-shell"><div class="ade-reco-list-head"><div class="ade-reco-list-title">{title}</div><div class="ade-reco-list-sub">{meta or "저장된 추천결과를 검증 가능한 근거 중심으로 봅니다."}</div></div>', unsafe_allow_html=True)
    _render_recommendation_generation(market, context)

    if not recommendations:
        st.markdown('<div class="ade-reco-list-card">저장된 추천 결과가 없습니다.</div></div>', unsafe_allow_html=True)
        return

    for row in recommendations:
        ticker = str(row.get("ticker"))
        symbol = str(row.get("symbol") or row.get("name") or ticker)
        rank = int(row.get("rank_no") or 0)
        score = float(row.get("score") or row.get("final_similarity") or row.get("weekly_similarity") or 0)
        sto = float(row.get("sto_similarity") or 0)
        payload = base_app._safe_json(row.get("payload_json"))
        replay_matches = [item for item in (payload.get("replay_matches") or []) if isinstance(item, dict)]
        success, neutral, fail, _, _ = _replay_summary(replay_matches)
        reason = _render_recommendation_reason(payload, row)
        tone = "good" if success > fail else ("bad" if fail > success else "neutral")
        st.markdown(
            f'''<div class="ade-reco-list-card"><div class="ade-reco-list-top"><div class="ade-reco-rank">#{rank}</div><div><div class="ade-reco-name">{symbol}</div><div class="ade-reco-code">{ticker}</div></div><div class="ade-reco-stat"><div class="l">추천점수</div><div class="v">{score:.1f}</div></div><div class="ade-reco-stat optional"><div class="l">STO</div><div class="v">{sto:.1f}%</div></div><div class="ade-reco-stat {tone} optional"><div class="l">Replay</div><div class="v">{len(replay_matches)}건</div></div></div><div class="ade-reco-result-row"><div class="ade-reco-result-chip success">성공 {success}</div><div class="ade-reco-result-chip neutral">중립 {neutral}</div><div class="ade-reco-result-chip fail">실패 {fail}</div></div><div class="ade-reco-reason">{reason}</div></div>''',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns([5, 1])
        if c1.button(f"{symbol} 검증하기", key=f"detail_{market}_{ticker}", use_container_width=True):
            st.session_state.ade_recommendation_detail = ticker
            st.session_state.ade_show_heavy_charts = False
            st.rerun()
        if c2.button("주문", key=f"order_{market}_{ticker}", use_container_width=True):
            try:
                base_app._add_order_candidate(market, ticker, symbol)
            except Exception as exc:
                st.error(str(exc))
                continue
            st.session_state.ade_order_ticker = ticker
            base_app._reset_order_confirmation()
            base_app._navigate_primary("주문")
    st.markdown('</div>', unsafe_allow_html=True)


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
    base_app._render_recommendations = _render_recommendations
    base_app._render_recommendation_detail = _render_recommendation_detail
    base_app.run()


if __name__ == "__main__":
    run()
