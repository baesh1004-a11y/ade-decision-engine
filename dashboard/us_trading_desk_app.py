from __future__ import annotations

import os
import logging
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from dashboard.charts import CHART_CONFIG, build_trading_chart
from meta_score.validation_context import EnvironmentAdvisor
from trading.us_order_service import USTradingOrderService


LOGGER = logging.getLogger(__name__)


def _kst_text(value) -> str:
    if not value:
        return "-"
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    return parsed.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


@st.cache_data(ttl=30, max_entries=100, show_spinner=False)
def _load_us_chart(ticker: str) -> tuple[pd.DataFrame, str | None]:
    try:
        import yfinance as yf

        frame = yf.download(
            ticker, period="5d", interval="5m", auto_adjust=False,
            progress=False, threads=False, timeout=10,
        )
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        frame = frame.reset_index()
        date_column = "Datetime" if "Datetime" in frame.columns else "Date"
        frame = frame.rename(columns={date_column: "Date"})
        keep = [column for column in ["Date", "Open", "High", "Low", "Close", "Volume"] if column in frame.columns]
        return frame[keep].dropna(subset=["Close"]), None
    except Exception as exc:
        LOGGER.exception("US chart download failed for %s", ticker)
        return pd.DataFrame(), str(exc)


def run(db_path: str = "datahub/us_market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE US Trading Desk", page_icon="🇺🇸", layout="wide")
    _style(st)

    env = os.getenv("KIS_ENV", "paper").lower()
    live_enabled = os.getenv("KIS_US_LIVE_ORDER_ENABLED", "NO").upper() == "YES"
    if env == "live":
        if live_enabled:
            st.error("미국 실전주문 모드가 활성화되어 있습니다.")
        else:
            st.warning("KIS_ENV=live이지만 미국 실전주문은 잠겨 있습니다.")
    else:
        st.info("현재 KIS 미국주식 모의투자 모드입니다. 모의투자는 지정가 주문만 지원합니다.")

    service = USTradingOrderService(db_path)
    try:
        recommendations = service.latest_recommendations(50)
        st.markdown("### 1. 추천 종목 주문 리스트")
        if not recommendations:
            st.warning("저장된 미국 추천 결과가 없습니다. US Daily Center에서 추천을 먼저 생성하세요.")
        else:
            st.caption("최신 추천 실행의 모든 종목을 주문 리스트에 포함합니다.")
            st.dataframe(_order_list_frame(recommendations), width="stretch", hide_index=True)

            labels = [
                f"#{row['rank_no']} {row.get('name') or row['ticker']} ({row['ticker']}) · "
                f"{_decision_label(str(row.get('decision') or 'UNVALIDATED'))}"
                for row in recommendations
            ]
            selected_from_workbench = str(st.session_state.get("workbench_selected_us") or "").upper()
            default_index = next(
                (index for index, row in enumerate(recommendations) if str(row["ticker"]).upper() == selected_from_workbench),
                0,
            )
            selected_index = st.selectbox(
                "주문·차트 확인 종목",
                range(len(recommendations)),
                index=default_index,
                format_func=lambda index: labels[index],
                key="trading_order_selected_us",
            )
            selected = recommendations[selected_index]
            ticker = str(selected["ticker"]).upper()
            st.session_state["workbench_selected_us"] = ticker

            _render_live_chart(st, ticker, selected.get("name") or ticker)
            _render_analysis_actions(st, selected, ticker)
            _render_order_form(st, service, selected, ticker)

        _render_pending(st, service, recommendations)
        _render_execution(st, service)
    finally:
        service.close()


def _order_list_frame(recommendations: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "순위": int(row["rank_no"]),
            "종목": row.get("name") or row["ticker"],
            "티커": str(row["ticker"]).upper(),
            "검증 조언": _decision_label(str(row.get("decision") or "UNVALIDATED")),
            "주문 상태": "주문 가능",
        }
        for row in recommendations
    ])


def _render_live_chart(st, ticker: str, label: str) -> None:
    st.markdown(f"### 현재 차트 · {label} ({ticker})")
    frame, error = _load_us_chart(ticker)

    if frame.empty:
        st.warning("현재 차트 데이터를 불러오지 못했습니다.")
        if error:
            with st.expander("오류 원인 확인"):
                st.code(error)
    else:
        st.plotly_chart(build_trading_chart(frame, f"{label} ({ticker})"), width="stretch", config=CHART_CONFIG)
        st.caption("Yahoo Finance 5분봉 · 종목을 변경하거나 새로고침하면 최신 데이터를 다시 조회합니다.")
    if st.button("현재 차트 새로고침", width="stretch", key=f"refresh_us_chart_{ticker}"):
        _load_us_chart.clear()
        st.rerun()


def _render_analysis_actions(st, selected: dict, ticker: str) -> None:
    st.markdown("### 추천 분석 연결")
    c1, c2 = st.columns(2)
    if c1.button("JP Radar 확인", width="stretch", key=f"us_jp_radar_{ticker}"):
        recommendation = SimpleNamespace(
            market="us",
            ticker=ticker,
            name=selected.get("name"),
            prediction=None,
            matched_max_drawdown=0.0,
        )
        st.session_state[f"us_jp_radar_result_{ticker}"] = EnvironmentAdvisor().analyze(recommendation)
    if c2.button("추천종목 검증 조언 확인", width="stretch", key=f"us_validation_{ticker}"):
        st.session_state[f"us_validation_open_{ticker}"] = True

    radar = st.session_state.get(f"us_jp_radar_result_{ticker}")
    if radar is not None:
        a, b = st.columns(2)
        a.metric("전체 시장 JP Radar", str(radar.market_signal))
        b.metric("해당 업종 JP Radar", str(radar.sector_signal))

    if st.session_state.get(f"us_validation_open_{ticker}"):
        st.markdown(f"**추천 검증 조언:** {_decision_label(str(selected.get('decision') or 'UNVALIDATED'))}")
        if str(selected.get("decision") or "UNVALIDATED") == "UNVALIDATED":
            st.info("아직 저장된 검증 조언이 없습니다. 통합 추천 워크벤치에서 환경 조언을 실행하세요.")


def _render_order_form(st, service, selected: dict, ticker: str) -> None:
    st.markdown("### 일반 주문")
    default_exchange = service.exchange_for_ticker(ticker)
    with st.form(f"us_order_form_{ticker}"):
        c1, c2, c3, c4 = st.columns(4)
        side = c1.selectbox("주문 방향", ["BUY", "SELL"], key=f"us_side_{ticker}")
        exchange = c2.selectbox(
            "거래소", ["NASD", "NYSE", "AMEX"],
            index=["NASD", "NYSE", "AMEX"].index(default_exchange), key=f"us_exchange_{ticker}",
        )
        quantity = c3.number_input("수량", min_value=1, value=1, step=1, key=f"us_quantity_{ticker}")
        limit_price = c4.number_input(
            "지정가(USD)", min_value=0.01, value=1.00, step=0.01, format="%.2f", key=f"us_price_{ticker}"
        )
        r1, r2 = st.columns(2)
        target = r1.number_input(
            "익절 기준 수익률(%)", value=float(selected.get("target_return") or 0.0), step=0.1, key=f"us_target_{ticker}"
        )
        stop = r2.number_input(
            "손절 기준 수익률(%)", value=float(selected.get("stop_return") or 0.0), step=0.1, key=f"us_stop_{ticker}"
        )
        submitted = st.form_submit_button("미국주식 주문 요청 만들기", type="primary", width="stretch")
    if submitted:
        try:
            request_id = service.create_request(
                ticker=ticker,
                name=selected.get("name"),
                exchange=exchange,
                side=side,
                quantity=int(quantity),
                limit_price=float(limit_price),
                target_return=float(target),
                stop_return=float(stop),
                source_run_id=str(selected["run_id"]),
                source_rank=int(selected["rank_no"]),
            )
            st.success(f"주문 요청 생성: {request_id}. 아직 KIS로 전송되지 않았습니다.")
        except Exception as exc:
            st.error(f"주문 요청 생성 실패: {exc}")


def _render_pending(st, service, recommendations: list[dict]) -> None:
    st.markdown("### 2. 사용자 승인 후 KIS 전송")
    pending = service.pending_approval_requests()
    current_run_id = str(recommendations[0]["run_id"]) if recommendations else ""
    if not pending:
        st.caption("승인 대기 주문이 없습니다.")
        return
    request_index = st.selectbox(
        "승인 대기 주문",
        range(len(pending)),
        format_func=lambda index: (
            ("현재 실행 · " if str(pending[index].get("source_run_id") or "") == current_run_id else "이전 실행 · ")
            + f"{pending[index]['ticker']} {pending[index]['side']} {pending[index]['quantity']}주 "
            f"${float(pending[index]['limit_price']):.2f} · {pending[index].get('created_at') or '-'}"
        ),
    )
    row = pending[request_index]
    if str(row.get("source_run_id") or "") != current_run_id:
        st.warning("이 주문은 이전 추천 실행에서 생성되었습니다. 현재 가격과 판단을 다시 확인하세요.")
    expected = f"{row['ticker']} {row['side']} {row['quantity']}주 ${float(row['limit_price']):.2f} 승인"
    st.code(expected)
    approval = st.text_input("위 승인 문구를 정확히 입력")
    confirm = st.checkbox("종목·거래소·방향·수량·지정가를 확인했습니다.")
    approve_col, cancel_col = st.columns(2)
    if approve_col.button("승인하고 KIS 미국주식 주문 전송", disabled=not confirm, type="primary"):
        try:
            result = service.approve_and_send(str(row["request_id"]), approval)
            st.success(f"주문 결과: {result.get('message')} · 주문번호 {result.get('order_id')}")
            st.rerun()
        except Exception as exc:
            st.error(f"주문 전송 실패: {exc}")
    if cancel_col.button("이 주문 요청 취소"):
        try:
            service.cancel_request(str(row["request_id"]))
            st.success("주문 요청을 취소했습니다.")
            st.rerun()
        except Exception as exc:
            st.error(f"주문 취소 실패: {exc}")


def _render_execution(st, service) -> None:
    st.markdown("### 3. 체결·보유종목·손절익절")
    c1, c2, c3 = st.columns(3)
    if c1.button("미국 주문·체결 새로고침", width="stretch"):
        try:
            rows = service.refresh_executions(days=7)
            st.success(f"최근 주문·체결 {len(rows)}건 확인")
        except Exception as exc:
            st.error(f"체결 조회 실패: {exc}")
    if c2.button("미국 보유종목 동기화", width="stretch"):
        try:
            rows = service.sync_positions()
            st.success(f"미국 보유종목 {len(rows)}개 동기화")
            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"보유종목 동기화 실패: {exc}")
    create_sell = c3.checkbox("조건 충족 시 매도요청 생성", value=False)
    if st.button("미국 손절·익절 조건 점검", width="stretch"):
        try:
            actions = service.monitor_risk(create_sell_requests=create_sell)
            if actions:
                st.warning(f"조건 충족 {len(actions)}건")
                st.dataframe(pd.DataFrame(actions), width="stretch", hide_index=True)
            else:
                st.success("현재 손절·익절 조건 충족 종목이 없습니다.")
        except Exception as exc:
            st.error(f"위험관리 점검 실패: {exc}")

    st.markdown("### 미국 주문 요청 이력")
    order_df = pd.DataFrame(service.order_history(100))
    if not order_df.empty:
        order_df["created_at"] = order_df["created_at"].map(_kst_text)
        keep = [column for column in [
            "created_at", "ticker", "name", "exchange", "side", "quantity", "limit_price",
            "status", "broker_order_id", "broker_message", "error_message",
        ] if column in order_df.columns]
        st.dataframe(order_df[keep], width="stretch", hide_index=True)

    st.markdown("### 미국 체결 이력")
    execution_df = pd.DataFrame(service.execution_history(100))
    if not execution_df.empty:
        execution_df["captured_at"] = execution_df["captured_at"].map(_kst_text)
        keep = [column for column in [
            "captured_at", "broker_order_id", "ticker", "exchange", "side", "ordered_quantity",
            "filled_quantity", "filled_price", "status",
        ] if column in execution_df.columns]
        st.dataframe(execution_df[keep], width="stretch", hide_index=True)
    st.caption("모의투자에서도 주문은 사용자 승인 후에만 전송됩니다.")


def _decision_label(value: str) -> str:
    return {
        "FINAL BUY": "매수 검토",
        "BUY WATCH": "관찰",
        "HOLD": "보류",
        "PASS": "제외",
        "UNVALIDATED": "미검증",
    }.get(value, value)


def _style(st) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1800px;padding-top:1rem}
        .hero{padding:24px 28px;border-radius:26px;background:rgba(255,255,255,.86);border:1px solid rgba(72,145,210,.22);box-shadow:0 18px 48px rgba(64,106,147,.12);margin-bottom:16px}
        .hero h1{margin:3px 0}.hero p{margin:5px 0;color:#687d92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        </style>
        <div class="hero"><div class="eyebrow">ADE · KIS US STOCK EXECUTION</div><h1>US Trading Desk</h1><p>추천 전 종목 주문 리스트 → 현재 차트 → JP Radar·검증 조언 → 지정가 주문 → 사용자 승인</p></div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    run()
