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
    _style(st)

    env = os.getenv("KIS_ENV", "paper").lower()
    live_enabled = os.getenv("KIS_LIVE_ORDER_ENABLED", "NO").upper() == "YES"
    if env == "live":
        if live_enabled:
            st.error("실전 주문 모드가 활성화되어 있습니다. 승인 문구를 입력하면 실제 주문이 전송됩니다.")
        else:
            st.warning("KIS_ENV=live이지만 실전 주문은 잠겨 있습니다. KIS_LIVE_ORDER_ENABLED=YES일 때만 전송됩니다.")
    else:
        st.info("현재 KIS 모의투자 주문 모드입니다.")

    service = TradingOrderService(db_path)
    try:
        recommendations = service.latest_recommendations(50)
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

            labels = [
                f"#{r['rank_no']} {display_symbol(r.get('name'), r['ticker'], 'kr')} · "
                f"{_decision_label(str(r['decision']))}"
                for r in recommendations
            ]
            selected_from_workbench = normalize_ticker(st.session_state.get("workbench_selected_kr") or "", "kr")
            default_index = next(
                (i for i, row in enumerate(recommendations) if normalize_ticker(row["ticker"], "kr") == selected_from_workbench),
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
                st.caption(f"총 {len(recommendations)}개 추천 종목")

            selected = recommendations[index]
            selected_code = normalize_ticker(selected["ticker"], "kr")
            selected_label = display_symbol(selected.get("name"), selected_code, "kr")
            st.session_state["workbench_selected_kr"] = selected_code

            with detail_column:
                _render_selected_summary(st, selected, selected_label)
                _render_analysis_actions(st, selected, selected_code)
                _render_live_chart(st, db_path, selected_code, selected_label)

            st.divider()
            _render_order_form(st, service, selected, selected_code, selected_label, run_id)

        _render_pending_approval(st, service, recommendations)
        _render_execution_and_history(st, service)
    finally:
        service.close()


def _render_selected_summary(st, selected: dict, label: str) -> None:
    st.markdown(f"### {label}")
    decision = str(selected.get("decision") or "UNVALIDATED")
    cols = st.columns(4)
    cols[0].metric("추천 순위", f"{int(selected.get('rank_no') or 0)}위")
    cols[1].metric("주봉 유사도", f"{float(selected.get('weekly_similarity') or 0.0):.2f}%")
    cols[2].metric("STO", f"{float(selected.get('sto_similarity') or 0.0):.2f}%")
    cols[3].metric("검증 조언", _decision_label(decision))


def _order_list_frame(recommendations: list[dict]) -> pd.DataFrame:
    rows = []
    for row in recommendations:
        rows.append(
            {
                "순위": int(row["rank_no"]),
                "종목": display_symbol(row.get("name"), row["ticker"], "kr"),
                "종목코드": normalize_ticker(row["ticker"], "kr"),
                "주봉 유사도": round(float(row.get("weekly_similarity") or 0.0), 2),
                "STO": round(float(row.get("sto_similarity") or 0.0), 2),
                "검증 조언": _decision_label(str(row.get("decision") or "UNVALIDATED")),
                "주문 상태": "주문 가능" if str(row.get("decision")) in ELIGIBLE_DECISIONS else "사용자 확인 필요",
            }
        )
    return pd.DataFrame(rows)


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
            keep = [column for column in ["Date", "Open", "High", "Low", "Close", "Volume"] if column in frame.columns]
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
    if str(ticker).endswith(".KS"):
        return f"{code}.KS"
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
        context = EnvironmentAdvisor().analyze(recommendation)
        st.session_state[f"jp_radar_result_{ticker}"] = context

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
        market_score = selected.get("market_score")
        sector_score = selected.get("sector_score")
        risk_score = selected.get("risk_score")
        st.markdown(f"**추천 검증 조언:** {_decision_label(decision)}")
        cols = st.columns(3)
        cols[0].metric("전체 시장", _score_label(market_score))
        cols[1].metric("해당 업종", _score_label(sector_score))
        cols[2].metric("종목 위험", _risk_label(risk_score))
        if decision == "UNVALIDATED":
            st.info("아직 저장된 검증 조언이 없습니다. 통합 추천 워크벤치에서 이 종목의 환경 조언을 실행하세요.")
            st.page_link("pages/2_Meta_Score.py", label="추천 검증 화면 열기", icon="✅", use_container_width=True)


def _render_order_form(st, service, selected: dict, ticker: str, label: str, run_id: str) -> None:
    st.markdown("### 일반 주문")
    decision = str(selected.get("decision") or "UNVALIDATED")
    validated = bool(selected.get("validation_available"))
    eligible = decision in ELIGIBLE_DECISIONS

    st.markdown(f"**선택 종목:** {label}")
    c1, c2, c3, c4 = st.columns(4)
    side = c1.selectbox("주문 방향", ["BUY", "SELL"], key=f"side_{ticker}")
    quantity = c2.number_input("수량", min_value=1, value=1, step=1, key=f"quantity_{ticker}")
    order_type = c3.selectbox("주문 유형", ["MARKET", "LIMIT"], key=f"order_type_{ticker}")
    limit_price = c4.number_input(
        "지정가",
        min_value=0.0,
        value=0.0,
        step=10.0,
        disabled=order_type == "MARKET",
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

    if not validated:
        st.caption("미검증 종목도 주문 리스트와 주문 입력은 유지됩니다. 매수 요청 전 검증 조언 확인을 권장합니다.")
    elif not eligible and side == "BUY":
        st.warning(f"현재 검증 조언은 {_decision_label(decision)}입니다. 주문 전 사용자가 직접 판단해야 합니다.")

    if st.button("주문 요청 만들기", type="primary", use_container_width=True, key=f"create_order_{ticker}"):
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
        keep = [column for column in [
            "created_at", "source_run_id", "source_rank", "종목", "종목코드", "side", "quantity",
            "order_type", "limit_price", "status", "broker_order_id", "broker_message", "error_message",
        ] if column in history.columns]
        st.dataframe(history[keep], use_container_width=True, hide_index=True)

    st.markdown("### 체결 이력")
    executions = pd.DataFrame(service.latest_executions(100))
    if not executions.empty:
        executions["종목코드"] = executions["ticker"].map(lambda value: normalize_ticker(value, "kr"))
        keep = [column for column in [
            "captured_at", "broker_order_id", "종목코드", "side", "ordered_quantity",
            "filled_quantity", "filled_price", "status",
        ] if column in executions.columns]
        st.dataframe(executions[keep], use_container_width=True, hide_index=True)

    st.caption("손절·익절 감시는 자동 매도를 직접 전송하지 않고 승인 대기 매도요청만 생성합니다.")


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
        .block-container{max-width:1800px;padding-top:1rem}
        .hero{padding:24px 28px;border-radius:26px;background:rgba(255,255,255,.86);border:1px solid rgba(72,145,210,.22);box-shadow:0 18px 48px rgba(64,106,147,.12);margin-bottom:16px}
        .hero h1{margin:3px 0}.hero p{margin:5px 0;color:#687d92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        div[role="radiogroup"]{gap:.35rem}
        div[role="radiogroup"] label{padding:.55rem .7rem;border:1px solid rgba(72,145,210,.18);border-radius:12px;background:rgba(255,255,255,.7)}
        </style>
        <div class="hero"><div class="eyebrow">ADE · 추천 전 종목 주문 연계</div><h1>한국 주문관리</h1><p>추천 Watch List → 선택 종목 판단 도구·차트 → 일반 주문 → 사용자 승인 → KIS 전송</p></div>
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
