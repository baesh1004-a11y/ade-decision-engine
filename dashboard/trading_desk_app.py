from __future__ import annotations

import argparse
import os

import pandas as pd

from trading.order_service import TradingOrderService


ELIGIBLE_DECISIONS = {"FINAL BUY", "BUY WATCH"}


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 한국 주문관리", page_icon="💳", layout="wide")
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1600px;padding-top:1rem}
        .hero{padding:24px 28px;border-radius:26px;background:rgba(255,255,255,.86);border:1px solid rgba(72,145,210,.22);box-shadow:0 18px 48px rgba(64,106,147,.12);margin-bottom:16px}
        .hero h1{margin:3px 0}.hero p{margin:5px 0;color:#687d92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        </style>
        <div class="hero"><div class="eyebrow">ADE · 최신 추천 실행 연계</div><h1>한국 주문관리</h1><p>통합 추천 워크벤치의 최신 완료 실행 → 추천 검증 → 주문 요청 → 사용자 승인 → KIS 전송</p></div>
        """,
        unsafe_allow_html=True,
    )

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
        recommendations = service.latest_recommendations(30)
        st.markdown("### 1. 최신 추천 실행에서 주문 요청 생성")
        if not recommendations:
            st.warning("최신 완료 추천 결과가 없습니다. 먼저 '한국 추천종목' 또는 '통합 추천 워크벤치'에서 추천을 생성하세요.")
        else:
            run_id = str(recommendations[0]["run_id"])
            run_finished = str(recommendations[0].get("run_finished_at") or "-")
            st.caption(f"연결 실행 ID: {run_id} · 완료 시각: {run_finished} · 통합 워크벤치와 동일한 최신 완료 실행")

            labels = [
                f"#{r['rank_no']} {r['name'] or r['ticker']} ({r['ticker']}) · "
                f"주봉 {float(r['weekly_similarity']):.2f}% · STO {float(r['sto_similarity']):.2f}% · "
                f"{_decision_label(str(r['decision']))}"
                for r in recommendations
            ]
            selected_from_workbench = str(st.session_state.get("workbench_selected_kr") or "")
            default_index = next(
                (i for i, row in enumerate(recommendations) if str(row["ticker"]) == selected_from_workbench),
                0,
            )
            index = st.selectbox(
                "최신 추천 후보",
                range(len(recommendations)),
                index=default_index,
                format_func=lambda i: labels[i],
            )
            selected = recommendations[index]
            decision = str(selected["decision"])
            validated = bool(selected.get("validation_available"))
            eligible = decision in ELIGIBLE_DECISIONS

            if selected_from_workbench and str(selected["ticker"]) == selected_from_workbench:
                st.success(f"통합 추천 워크벤치에서 선택한 종목 {selected['name'] or selected['ticker']}이 연결되었습니다.")
            if not validated:
                st.warning("이 최신 추천 실행은 아직 추천 검증이 완료되지 않았습니다. 검증 후 주문 요청을 만들 수 있습니다.")
                st.page_link("pages/2_Meta_Score.py", label="한국 추천 검증 열기", icon="✅", use_container_width=True)
            elif not eligible:
                st.warning(f"현재 검증 결과는 {_decision_label(decision)}이므로 매수 주문 대상이 아닙니다.")

            c1, c2, c3, c4 = st.columns(4)
            side = c1.selectbox("주문 방향", ["BUY", "SELL"])
            quantity = c2.number_input("수량", min_value=1, value=1, step=1)
            order_type = c3.selectbox("주문 유형", ["MARKET", "LIMIT"])
            limit_price = c4.number_input("지정가", min_value=0.0, value=0.0, step=10.0, disabled=order_type == "MARKET")
            r1, r2 = st.columns(2)
            target = r1.number_input("익절 기준 수익률(%)", value=float(selected.get("target_return") or 0.0), step=0.1)
            stop = r2.number_input("손절 기준 수익률(%)", value=float(selected.get("stop_return") or 0.0), step=0.1)

            request_allowed = validated and (eligible or side == "SELL")
            if st.button("주문 요청 만들기", type="primary", use_container_width=True, disabled=not request_allowed):
                request_id = service.create_request(
                    ticker=str(selected["ticker"]),
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

        st.markdown("### 2. 사용자 승인 후 KIS 주문 전송")
        requests = service.pending_requests(100)
        pending = [r for r in requests if r["status"] == "PENDING_APPROVAL"]
        if not pending:
            st.caption("승인 대기 주문이 없습니다.")
        else:
            request_index = st.selectbox(
                "승인 대기 주문",
                range(len(pending)),
                format_func=lambda i: f"{pending[i]['name'] or pending[i]['ticker']} · {pending[i]['ticker']} {pending[i]['side']} {pending[i]['quantity']}주",
            )
            row = pending[request_index]
            expected = f"{row['ticker']} {row['side']} {row['quantity']}주 승인"
            st.code(expected)
            approval = st.text_input("위 승인 문구를 정확히 입력")
            confirm = st.checkbox("종목·방향·수량·주문유형을 직접 확인했습니다.")
            if st.button("승인하고 KIS로 전송", disabled=not confirm, type="primary"):
                try:
                    result = service.approve_and_send(str(row["request_id"]), approval)
                    st.success(f"주문 전송 결과: {result.get('message')} · 주문번호 {result.get('order_id')}")
                except Exception as exc:
                    st.error(f"주문 전송 실패: {exc}")

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
            keep = [c for c in ["created_at", "source_run_id", "source_rank", "ticker", "name", "side", "quantity", "order_type", "limit_price", "status", "broker_order_id", "broker_message", "error_message"] if c in history.columns]
            st.dataframe(history[keep], use_container_width=True, hide_index=True)

        st.markdown("### 체결 이력")
        executions = pd.DataFrame(service.latest_executions(100))
        if not executions.empty:
            keep = [c for c in ["captured_at", "broker_order_id", "ticker", "side", "ordered_quantity", "filled_quantity", "filled_price", "status"] if c in executions.columns]
            st.dataframe(executions[keep], use_container_width=True, hide_index=True)

        st.caption("손절·익절 감시는 자동 매도를 직접 전송하지 않고 승인 대기 매도요청만 생성합니다.")
    finally:
        service.close()


def _decision_label(value: str) -> str:
    return {
        "FINAL BUY": "매수 검토",
        "BUY WATCH": "관찰",
        "HOLD": "보류",
        "PASS": "제외",
        "UNVALIDATED": "미검증",
    }.get(value, value)


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE 한국 주문관리")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
