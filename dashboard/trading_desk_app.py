from __future__ import annotations

import argparse
import os
import sqlite3
from types import SimpleNamespace

import pandas as pd

from dashboard.charts import CHART_CONFIG, build_trading_chart
from markets.symbol_display import display_symbol, normalize_ticker
from meta_score.validation_context import EnvironmentAdvisor
from trading.order_service import TradingOrderService


ELIGIBLE_DECISIONS = {"FINAL BUY", "BUY WATCH"}


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

        st.markdown("### 1. 추천 Watch List")
        if not recommendations:
            st.warning("최신 완료 추천 결과가 없습니다. 먼저 통합 추천 워크벤치에서 추천을 생성하세요.")
        else:
            run_id = str(recommendations[0]["run_id"])
            run_finished = str(recommendations[0].get("run_finished_at") or "-")
            st.caption(
                f"추천 완료: {run_finished} · "
                "왼쪽 목록에서 종목을 선택하면 오른쪽 차트와 분석·주문 화면이 함께 바뀝니다."
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

            watch_column, detail_column = st.columns([1, 3], gap="large")
            with watch_column:
                st.markdown("#### 추천 종목")
                index = st.radio(
                    "추천 종목 선택",
                    range(len(recommendations)),
                    index=default_index,
                    format_func=lambda i: labels[i],
                    key="trading_order_selected_kr",
                    label_visibility="collapsed",
                )
                st.caption("● 매수 검토  ● 관찰  ● 보류  ● 제외  ● 미검증")
                st.caption(f"총 {len(recommendations)}개 추천 종목")

            selected = recommendations[index]
            selected_code = normalize_ticker(selected["ticker"], "kr")
            selected_label = display_symbol(selected.get("name"), selected_code, "kr")
            st.session_state["workbench_selected_kr"] = selected_code

            with detail_column:
                _render_selected_summary(st, selected, selected_label)
                _render_ai_confidence_card(st, selected, selected_code)
                _render_analysis_actions(st, selected, selected_code)
                _render_live_chart(st, db_path, selected_code, selected_label)

            st.divider()
            _render_order_form(st, service, selected, selected_code, selected_label, run_id)

        _render_pending_approval(st, service, recommendations)
        _render_execution_and_history(st, service)
    finally:
        service.close()


def _render_status_header(st, env: str, live_enabled: bool, recommendation_count: int, pending_count: int) -> None:
    if env == "live" and live_enabled:
        mode_label = "실전주문 활성"
        mode_class = "danger"
    elif env == "live":
        mode_label = "실전환경 · 주문 잠금"
        mode_class = "warning"
    else:
        mode_label = "모의투자"
        mode_class = "safe"

    st.markdown(
        f"""
        <div class="status-hero">
          <div>
            <div class="eyebrow">ADE · 추천 전 종목 주문 연계</div>
            <h1>한국 주문관리</h1>
            <p>추천 Watch List → 선택 종목 판단 도구·차트 → 일반 주문 → 사용자 승인 → KIS 전송</p>
          </div>
          <div class="status-cluster">
            <span class="status-badge {mode_class}">● {mode_label}</span>
            <span class="status-badge neutral">추천 {recommendation_count}종목</span>
            <span class="status-badge neutral">승인 대기 {pending_count}건</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _watch_label(row: dict) -> str:
    decision = str(row.get("decision") or "UNVALIDATED")
    marker = _decision_marker(decision)
    name = display_symbol(row.get("name"), row.get("ticker"), "kr")
    rank = int(row.get("rank_no") or 0)
    weekly = float(row.get("weekly_similarity") or 0.0)
    sto = float(row.get("sto_similarity") or 0.0)
    return (
        f"{marker} #{rank} {name} · {_decision_label(decision)}\n"
        f"주봉 {weekly:.1f}%  ·  STO {sto:.1f}%"
    )


def _render_selected_summary(st, selected: dict, label: str) -> None:
    st.markdown(f"### {label}")
    decision = str(selected.get("decision") or "UNVALIDATED")
    cols = st.columns(4)
    cols[0].metric("추천 순위", f"{int(selected.get('rank_no') or 0)}위")
    cols[1].metric("주봉 유사도", f"{float(selected.get('weekly_similarity') or 0.0):.2f}%")
    cols[2].metric("STO", f"{float(selected.get('sto_similarity') or 0.0):.2f}%")
    cols[3].metric("검증 조언", _decision_label(decision))


def _render_ai_confidence_card(st, selected: dict, ticker: str) -> None:
    score, level, tone, opinion, factors = _ai_confidence(selected, st.session_state.get(f"jp_radar_result_{ticker}"))
    rows = "".join(
        f'<div class="confidence-row"><span>{label}</span><strong>{value}</strong><span class="signal {signal}">●</span></div>'
        for label, value, signal in factors
    )
    st.markdown(
        f"""
        <div class="confidence-card {tone}">
          <div class="confidence-head">
            <div>
              <div class="confidence-eyebrow">AI 종합 판단 보조</div>
              <div class="confidence-title">{_confidence_icon(tone)} AI 신뢰도 · {level}</div>
            </div>
            <div class="confidence-score">{score}<span>점</span></div>
          </div>
          <div class="confidence-grid">{rows}</div>
          <div class="confidence-opinion"><strong>AI 종합 의견</strong><br>{opinion}</div>
          <div class="confidence-note">기존 추천·검증 데이터를 요약한 참고 지표이며 투자 판단이나 주문 승인을 대신하지 않습니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _ai_confidence(selected: dict, radar) -> tuple[int, str, str, str, list[tuple[str, str, str]]]:
    weekly = _clamp_score(selected.get("weekly_similarity"))
    sto = _clamp_score(selected.get("sto_similarity"))
    market = _clamp_score(selected.get("market_score"), default=50.0)
    sector = _clamp_score(selected.get("sector_score"), default=50.0)
    risk = _clamp_score(selected.get("risk_score"), default=50.0)

    radar_score = 50.0
    radar_label = "미확인"
    if radar is not None:
        market_signal = str(getattr(radar, "market_signal", "") or "")
        sector_signal = str(getattr(radar, "sector_signal", "") or "")
        radar_text = f"{market_signal} {sector_signal}".lower()
        if any(token in radar_text for token in ("강세", "positive", "bull", "양호")):
            radar_score, radar_label = 80.0, "강세"
        elif any(token in radar_text for token in ("약세", "negative", "bear", "주의")):
            radar_score, radar_label = 30.0, "약세"
        else:
            radar_score, radar_label = 55.0, "중립"

    score = round(
        weekly * 0.28
        + sto * 0.22
        + market * 0.16
        + sector * 0.14
        + risk * 0.15
        + radar_score * 0.05
    )

    decision = str(selected.get("decision") or "UNVALIDATED")
    if decision == "FINAL BUY":
        score = min(100, score + 5)
    elif decision in {"HOLD", "PASS"}:
        score = max(0, score - 10)
    elif decision == "UNVALIDATED":
        score = min(score, 69)

    if score >= 80:
        level, tone = "매우 높음", "high"
        opinion = "현재 데이터는 적극적인 매수 검토가 가능한 구간을 가리킵니다. 주문 전 차트와 검증 조언을 함께 확인하세요."
    elif score >= 65:
        level, tone = "높음", "good"
        opinion = "긍정 신호가 우세하지만 일부 조건 확인이 필요합니다. 분할 접근과 위험 기준 확인이 적절합니다."
    elif score >= 45:
        level, tone = "보통", "neutral"
        opinion = "신호가 혼재되어 있습니다. 추가 검증 전에는 관찰 중심 접근이 적절합니다."
    else:
        level, tone = "낮음", "low"
        opinion = "위험 또는 약한 신호가 우세합니다. 현재는 관망과 재검증을 우선하는 편이 안전합니다."

    factors = [
        ("주봉 유사도", f"{weekly:.0f}%", _signal_class(weekly)),
        ("STO", f"{sto:.0f}%", _signal_class(sto)),
        ("JP Radar", radar_label, _signal_class(radar_score)),
        ("시장·업종", f"{(market + sector) / 2:.0f}점", _signal_class((market + sector) / 2)),
        ("리스크", _risk_label(risk), _signal_class(risk)),
    ]
    return score, level, tone, opinion, factors


def _clamp_score(value, default: float = 0.0) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return default


def _signal_class(score: float) -> str:
    return "high" if score >= 70 else "mid" if score >= 45 else "low"


def _confidence_icon(tone: str) -> str:
    return {"high": "🟢", "good": "🔵", "neutral": "🟠", "low": "🔴"}.get(tone, "⚪")


def _render_live_chart(st, db_path: str, ticker: str, label: str) -> None:
    st.markdown(f"### 현재 차트 · {label}")
    bars, source = _load_live_bars(db_path, ticker)
    if bars.empty:
        st.warning("현재 차트 데이터를 불러오지 못했습니다.")
        return
    st.plotly_chart(build_trading_chart(bars, label), use_container_width=True, config=CHART_CONFIG)
    st.caption(f"시세 출처: {source} · 종목을 변경하거나 새로고침하면 최신 데이터를 다시 조회합니다.")


def _load_live_bars(db_path: str, ticker: str) -> tuple[pd.DataFrame, str]:
    try:
        import yfinance as yf

        yahoo_ticker = _yahoo_ticker(ticker)
        frame = yf.download(
            yahoo_ticker,
            period="5d",
            interval="5m",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if not frame.empty:
            if isinstance(frame.columns, pd.MultiIndex):
                frame.columns = frame.columns.get_level_values(0)
            frame = frame.reset_index()
            date_column = "Datetime" if "Datetime" in frame.columns else "Date"
            frame = frame.rename(columns={date_column: "Date"})
            keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"] if c in frame.columns]
            return frame[keep].dropna(subset=["Close"]), f"Yahoo Finance 5분봉 ({yahoo_ticker})"
    except Exception:
        pass

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT trade_date AS Date, open AS Open, high AS High, low AS Low,
                      close AS Close, volume AS Volume
               FROM price_bars
               WHERE market='kr' AND ticker=?
               ORDER BY trade_date DESC LIMIT 120""",
            (ticker,),
        ).fetchall()
        return pd.DataFrame([dict(row) for row in reversed(rows)]), "내부 최신 저장 시세"
    finally:
        conn.close()


def _yahoo_ticker(ticker: str) -> str:
    code = normalize_ticker(ticker, "kr")
    if str(ticker).endswith(".KQ"):
        return f"{code}.KQ"
    return f"{code}.KS"


def _render_analysis_actions(st, selected: dict, ticker: str) -> None:
    st.markdown("#### 판단 도구")
    c1, c2, c3 = st.columns(3)
    if c1.button("JP Radar", use_container_width=True, key=f"jp_radar_{ticker}"):
        recommendation = SimpleNamespace(
            market="kr",
            ticker=ticker,
            name=selected.get("name"),
            prediction=None,
            matched_max_drawdown=float(selected.get("matched_max_drawdown") or 0.0),
        )
        st.session_state[f"jp_radar_result_{ticker}"] = EnvironmentAdvisor().analyze(recommendation)
        st.rerun()

    if c2.button("추천 검증", use_container_width=True, key=f"validation_{ticker}"):
        st.session_state[f"validation_open_{ticker}"] = True

    if c3.button("차트 새로고침", use_container_width=True, key=f"refresh_chart_{ticker}"):
        st.rerun()

    radar = st.session_state.get(f"jp_radar_result_{ticker}")
    if radar is not None:
        a, b = st.columns(2)
        a.metric("전체 시장 JP Radar", str(radar.market_signal))
        b.metric("해당 업종 JP Radar", str(radar.sector_signal))

    if st.session_state.get(f"validation_open_{ticker}"):
        decision = str(selected.get("decision") or "UNVALIDATED")
        st.markdown(f"**추천 검증 조언:** {_decision_label(decision)}")
        cols = st.columns(3)
        cols[0].metric("전체 시장", _score_label(selected.get("market_score")))
        cols[1].metric("해당 업종", _score_label(selected.get("sector_score")))
        cols[2].metric("종목 위험", _risk_label(selected.get("risk_score")))
        if decision == "UNVALIDATED":
            st.info("아직 저장된 검증 조언이 없습니다. 통합 추천 워크벤치에서 이 종목의 환경 조언을 실행하세요.")
            st.page_link("pages/2_Meta_Score.py", label="추천 검증 화면 열기", icon="✅", use_container_width=True)


def _render_order_form(st, service, selected: dict, ticker: str, label: str, run_id: str) -> None:
    st.markdown("### 일반 주문")
    decision = str(selected.get("decision") or "UNVALIDATED")
    validated = bool(selected.get("validation_available"))
    eligible = decision in ELIGIBLE_DECISIONS

    st.markdown(f"**선택 종목:** {label}")
    side_labels = {"매수": "BUY", "매도": "SELL"}
    order_type_labels = {"시장가": "MARKET", "지정가": "LIMIT"}

    c1, c2, c3 = st.columns([1, 1, 1.2])
    side_label = c1.selectbox("주문 방향", list(side_labels), key=f"side_label_{ticker}")
    quantity = c2.number_input("수량", min_value=1, value=1, step=1, key=f"quantity_{ticker}")
    order_type_label = c3.selectbox("주문 유형", list(order_type_labels), key=f"order_type_label_{ticker}")

    side = side_labels[side_label]
    order_type = order_type_labels[order_type_label]
    limit_price = 0.0
    if order_type == "LIMIT":
        limit_price = st.number_input(
            "지정가",
            min_value=0.0,
            value=0.0,
            step=10.0,
            key=f"limit_price_{ticker}",
        )

    r1, r2 = st.columns(2)
    target = r1.number_input(
        "익절 기준 수익률(%)",
        value=float(selected.get("target_return") or 0.0),
        step=0.1,
        key=f"target_{ticker}",
    )
    stop = r2.number_input(
        "손절 기준 수익률(%)",
        value=float(selected.get("stop_return") or 0.0),
        step=0.1,
        key=f"stop_{ticker}",
    )

    price_phrase = "시장가로" if order_type == "MARKET" else f"{float(limit_price):,.0f}원 지정가로"
    summary = f"{label} {int(quantity)}주를 {price_phrase} {side_label}합니다."
    risk_summary = f"목표 수익률 {float(target):+.1f}% · 손절 기준 {float(stop):+.1f}%"
    st.markdown(
        f"""
        <div class="order-summary">
          <div class="order-summary-label">주문 요약</div>
          <div class="order-summary-main">{summary}</div>
          <div class="order-summary-risk">{risk_summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not validated:
        st.caption("미검증 종목도 주문 리스트와 주문 입력은 유지됩니다. 매수 요청 전 검증 조언 확인을 권장합니다.")
    elif not eligible and side == "BUY":
        st.warning(f"현재 검증 조언은 {_decision_label(decision)}입니다. 주문 전 사용자가 직접 판단해야 합니다.")

    invalid_limit = order_type == "LIMIT" and float(limit_price) <= 0
    if invalid_limit:
        st.warning("지정가 주문은 0원보다 큰 가격을 입력해야 합니다.")

    if st.button(
        "주문 요청 만들기",
        type="primary",
        use_container_width=True,
        key=f"create_order_{ticker}",
        disabled=invalid_limit,
    ):
        request_id = service.create_request(
            ticker=ticker,
            name=selected.get("name"),
            side=side,
            quantity=int(quantity),
            order_type=order_type,
            limit_price=None if order_type == "MARKET" else float(limit_price),
            target_return=float(target),
            stop_return=float(stop),
            source_run_id=run_id,
            source_rank=int(selected["rank_no"]),
        )
        st.success(f"주문 요청 생성: {request_id}. 아직 KIS로 전송되지 않았습니다.")


def _render_pending_approval(st, service, recommendations: list[dict]) -> None:
    st.markdown("### 2. 사용자 승인 후 KIS 주문 전송")
    requests = service.pending_requests(100)
    current_run_id = str(recommendations[0]["run_id"]) if recommendations else ""
    pending = [
        row for row in requests
        if row["status"] == "PENDING_APPROVAL" and str(row.get("source_run_id") or "") == current_run_id
    ]
    if not pending:
        st.caption("현재 추천 실행의 승인 대기 주문이 없습니다.")
        return

    request_index = st.selectbox(
        "승인 대기 주문",
        range(len(pending)),
        format_func=lambda i: (
            f"{display_symbol(pending[i].get('name'), pending[i]['ticker'], 'kr')} · "
            f"{normalize_ticker(pending[i]['ticker'], 'kr')} {pending[i]['side']} {pending[i]['quantity']}주"
        ),
    )
    row = pending[request_index]
    code = normalize_ticker(row["ticker"], "kr")
    expected = f"{code} {row['side']} {row['quantity']}주 승인"
    st.code(expected)
    approval = st.text_input("위 승인 문구를 정확히 입력")
    confirm = st.checkbox("종목·방향·수량·주문유형을 직접 확인했습니다.")
    if st.button("승인하고 KIS로 전송", disabled=not confirm, type="primary"):
        try:
            result = service.approve_and_send(str(row["request_id"]), approval)
            st.success(f"주문 전송 결과: {result.get('message')} · 주문번호 {result.get('order_id')}")
        except Exception as exc:
            st.error(f"주문 전송 실패: {exc}")


def _render_execution_and_history(st, service) -> None:
    st.markdown("### 3. 주문 결과·체결 확인")
    a, b, c = st.columns(3)
    if a.button("체결내역 새로고침", use_container_width=True):
        try:
            rows = service.refresh_executions()
            st.success(f"KIS 주문·체결 {len(rows)}건 확인")
        except Exception as exc:
            st.error(f"체결 조회 실패: {exc}")
    if b.button("보유종목 자동 반영", use_container_width=True):
        try:
            rows = service.sync_positions()
            st.success(f"보유종목 {len(rows)}개 동기화")
        except Exception as exc:
            st.error(f"보유종목 동기화 실패: {exc}")
    create_sell = c.checkbox("손절·익절 발생 시 매도요청 생성", value=False)
    if st.button("손절·익절 조건 점검", use_container_width=True):
        try:
            actions = service.monitor_risk(create_sell_requests=create_sell)
            if actions:
                st.warning(f"조건 충족 {len(actions)}건")
                st.dataframe(pd.DataFrame(actions), use_container_width=True, hide_index=True)
            else:
                st.success("현재 손절·익절 조건 충족 종목이 없습니다.")
        except Exception as exc:
            st.error(f"위험관리 점검 실패: {exc}")

    st.markdown("### 주문 요청 이력")
    history = pd.DataFrame(service.pending_requests(100))
    if not history.empty:
        history["종목코드"] = history["ticker"].map(lambda value: normalize_ticker(value, "kr"))
        history["종목"] = history.apply(lambda row: display_symbol(row.get("name"), row.get("ticker"), "kr"), axis=1)
        keep = [c for c in [
            "created_at", "source_run_id", "source_rank", "종목", "종목코드", "side", "quantity",
            "order_type", "limit_price", "status", "broker_order_id", "broker_message", "error_message",
        ] if c in history.columns]
        st.dataframe(history[keep], use_container_width=True, hide_index=True)

    st.markdown("### 체결 이력")
    executions = pd.DataFrame(service.latest_executions(100))
    if not executions.empty:
        executions["종목코드"] = executions["ticker"].map(lambda value: normalize_ticker(value, "kr"))
        keep = [c for c in [
            "captured_at", "broker_order_id", "종목코드", "side", "ordered_quantity",
            "filled_quantity", "filled_price", "status",
        ] if c in executions.columns]
        st.dataframe(executions[keep], use_container_width=True, hide_index=True)

    st.caption("손절·익절 감시는 자동 매도를 직접 전송하지 않고 승인 대기 매도요청만 생성합니다.")


def _decision_marker(value: str) -> str:
    return {
        "FINAL BUY": "🟢",
        "BUY WATCH": "🔵",
        "HOLD": "🟠",
        "PASS": "⚪",
        "UNVALIDATED": "◽",
    }.get(value, "◽")


def _decision_label(value: str) -> str:
    return {
        "FINAL BUY": "매수 검토",
        "BUY WATCH": "관찰",
        "HOLD": "보류",
        "PASS": "제외",
        "UNVALIDATED": "미검증",
    }.get(value, value)


def _score_label(value) -> str:
    if value is None:
        return "미확인"
    score = float(value)
    return "양호" if score >= 70 else "보통" if score >= 45 else "주의"


def _risk_label(value) -> str:
    if value is None:
        return "미확인"
    score = float(value)
    return "낮음" if score >= 70 else "보통" if score >= 45 else "높음"


def _style(st) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1800px;padding-top:.75rem}
        .status-hero{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:18px 24px;border-radius:22px;background:rgba(255,255,255,.88);border:1px solid rgba(72,145,210,.22);box-shadow:0 14px 40px rgba(64,106,147,.11);margin-bottom:12px}
        .status-hero h1{margin:2px 0;font-size:2rem}.status-hero p{margin:3px 0;color:#687d92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        .status-cluster{display:flex;justify-content:flex-end;align-items:center;gap:8px;flex-wrap:wrap}
        .status-badge{display:inline-flex;align-items:center;padding:7px 11px;border-radius:999px;font-size:.84rem;font-weight:750;white-space:nowrap;border:1px solid transparent}
        .status-badge.safe{color:#137044;background:#e9f8f0;border-color:#bde8cf}
        .status-badge.warning{color:#986314;background:#fff6dd;border-color:#f0d58e}
        .status-badge.danger{color:#b42318;background:#fff0ef;border-color:#f3bbb6}
        .status-badge.neutral{color:#36516b;background:#f2f7fb;border-color:#d6e3ed}
        .confidence-card{margin:12px 0 16px;padding:17px 19px;border-radius:18px;background:rgba(255,255,255,.9);border:1px solid rgba(72,145,210,.24);box-shadow:0 10px 28px rgba(64,106,147,.09)}
        .confidence-card.high{border-left:6px solid #26a269}.confidence-card.good{border-left:6px solid #3479b9}.confidence-card.neutral{border-left:6px solid #d28b26}.confidence-card.low{border-left:6px solid #c43d36}
        .confidence-head{display:flex;align-items:center;justify-content:space-between;gap:18px}
        .confidence-eyebrow{font-size:.76rem;font-weight:800;letter-spacing:.09em;color:#6a8095;text-transform:uppercase}
        .confidence-title{margin-top:2px;font-size:1.16rem;font-weight:800;color:#17324d}
        .confidence-score{font-size:2rem;font-weight:850;line-height:1;color:#17324d}.confidence-score span{font-size:.85rem;margin-left:2px;color:#6d8194}
        .confidence-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:14px 0 10px}
        .confidence-row{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:6px;padding:9px 10px;border-radius:11px;background:#f5f9fc;font-size:.84rem;color:#5b7186}
        .confidence-row strong{color:#203a54}.signal.high{color:#26a269}.signal.mid{color:#d28b26}.signal.low{color:#c43d36}
        .confidence-opinion{padding:11px 13px;border-radius:12px;background:#eef6fc;color:#314d67;line-height:1.5}
        .confidence-note{margin-top:7px;font-size:.75rem;color:#7d8fa0}
        .order-summary{margin:14px 0 10px;padding:16px 18px;border-radius:16px;background:rgba(255,255,255,.86);border:1px solid rgba(72,145,210,.24);box-shadow:0 8px 24px rgba(64,106,147,.08)}
        .order-summary-label{font-size:.78rem;font-weight:800;letter-spacing:.08em;color:#3479b9;text-transform:uppercase;margin-bottom:5px}
        .order-summary-main{font-size:1.08rem;font-weight:760;color:#17324d}
        .order-summary-risk{margin-top:4px;color:#62788e;font-size:.93rem}
        div[role="radiogroup"]{gap:.45rem}
        div[role="radiogroup"] label{padding:.68rem .75rem;border:1px solid rgba(72,145,210,.18);border-radius:12px;background:rgba(255,255,255,.72);line-height:1.35}
        div[role="radiogroup"] label:hover{border-color:rgba(52,121,185,.48);background:rgba(239,248,255,.96)}
        @media(max-width:1100px){.confidence-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:900px){.status-hero{align-items:flex-start;flex-direction:column}.status-cluster{justify-content:flex-start}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE 한국 주문관리")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
