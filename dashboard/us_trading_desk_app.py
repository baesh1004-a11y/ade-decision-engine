from __future__ import annotations

import os

import pandas as pd

from trading.us_order_service import USTradingOrderService


def run(db_path: str = "datahub/us_market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE US Trading Desk", page_icon="🇺🇸", layout="wide")
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1600px;padding-top:1rem}
        .hero{padding:24px 28px;border-radius:26px;background:rgba(255,255,255,.86);border:1px solid rgba(72,145,210,.22);box-shadow:0 18px 48px rgba(64,106,147,.12);margin-bottom:16px}
        .hero h1{margin:3px 0}.hero p{margin:5px 0;color:#687d92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        </style>
        <div class="hero"><div class="eyebrow">ADE · KIS US STOCK EXECUTION</div><h1>US Trading Desk</h1><p>추천 → 지정가 주문요청 → 사용자 승인 → KIS 미국주식 모의주문 → 체결·잔고 확인</p></div>
        """,
        unsafe_allow_html=True,
    )

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
        st.markdown("### 1. 미국 추천종목 주문 요청")
        recommendations = service.latest_recommendations(30)
        if not recommendations:
            st.warning("저장된 미국 추천 결과가 없습니다. US Daily Center에서 추천을 먼저 생성하세요.")
        else:
            labels = [f"#{r['rank_no']} {r['name'] or r['ticker']} ({r['ticker']}) · {r['decision']}" for r in recommendations]
            selected_index = st.selectbox("미국 추천종목", range(len(recommendations)), format_func=lambda i: labels[i])
            selected = recommendations[selected_index]
            default_exchange = service.exchange_for_ticker(str(selected["ticker"]))

            c1, c2, c3, c4 = st.columns(4)
            side = c1.selectbox("주문 방향", ["BUY", "SELL"])
            exchange = c2.selectbox("거래소", ["NASD", "NYSE", "AMEX"], index=["NASD", "NYSE", "AMEX"].index(default_exchange))
            quantity = c3.number_input("수량", min_value=1, value=1, step=1)
            limit_price = c4.number_input("지정가(USD)", min_value=0.01, value=1.00, step=0.01, format="%.2f")

            r1, r2 = st.columns(2)
            target = r1.number_input("익절 기준 수익률(%)", value=float(selected.get("target_return") or 0.0), step=0.1)
            stop = r2.number_input("손절 기준 수익률(%)", value=float(selected.get("stop_return") or 0.0), step=0.1)

            if st.button("미국주식 주문 요청 만들기", type="primary", use_container_width=True):
                try:
                    request_id = service.create_request(
                        ticker=str(selected["ticker"]),
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

        st.markdown("### 2. 사용자 승인 후 KIS 전송")
        history = service.order_history(100)
        pending = [row for row in history if row["status"] == "PENDING_APPROVAL"]
        if not pending:
            st.caption("승인 대기 주문이 없습니다.")
        else:
            request_index = st.selectbox(
                "승인 대기 주문",
                range(len(pending)),
                format_func=lambda i: f"{pending[i]['ticker']} {pending[i]['side']} {pending[i]['quantity']}주 ${float(pending[i]['limit_price']):.2f}",
            )
            row = pending[request_index]
            expected = f"{row['ticker']} {row['side']} {row['quantity']}주 ${float(row['limit_price']):.2f} 승인"
            st.code(expected)
            approval = st.text_input("위 승인 문구를 정확히 입력")
            confirm = st.checkbox("종목·거래소·방향·수량·지정가를 확인했습니다.")
            if st.button("승인하고 KIS 미국주식 주문 전송", disabled=not confirm, type="primary"):
                try:
                    result = service.approve_and_send(str(row["request_id"]), approval)
                    st.success(f"주문 결과: {result.get('message')} · 주문번호 {result.get('order_id')}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"주문 전송 실패: {exc}")

        st.markdown("### 3. 체결·보유종목·손절익절")
        c1, c2, c3 = st.columns(3)
        if c1.button("미국 주문·체결 새로고침", use_container_width=True):
            try:
                rows = service.refresh_executions(days=7)
                st.success(f"최근 주문·체결 {len(rows)}건 확인")
            except Exception as exc:
                st.error(f"체결 조회 실패: {exc}")
        if c2.button("미국 보유종목 동기화", use_container_width=True):
            try:
                rows = service.sync_positions()
                st.success(f"미국 보유종목 {len(rows)}개 동기화")
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"보유종목 동기화 실패: {exc}")
        create_sell = c3.checkbox("조건 충족 시 매도요청 생성", value=False)
        if st.button("미국 손절·익절 조건 점검", use_container_width=True):
            try:
                actions = service.monitor_risk(create_sell_requests=create_sell)
                if actions:
                    st.warning(f"조건 충족 {len(actions)}건")
                    st.dataframe(pd.DataFrame(actions), use_container_width=True, hide_index=True)
                else:
                    st.success("현재 손절·익절 조건 충족 종목이 없습니다.")
            except Exception as exc:
                st.error(f"위험관리 점검 실패: {exc}")

        st.markdown("### 미국 주문 요청 이력")
        order_df = pd.DataFrame(service.order_history(100))
        if not order_df.empty:
            keep = [c for c in ["created_at", "ticker", "name", "exchange", "side", "quantity", "limit_price", "status", "broker_order_id", "broker_message", "error_message"] if c in order_df.columns]
            st.dataframe(order_df[keep], use_container_width=True, hide_index=True)

        st.markdown("### 미국 체결 이력")
        execution_df = pd.DataFrame(service.execution_history(100))
        if not execution_df.empty:
            keep = [c for c in ["captured_at", "broker_order_id", "ticker", "exchange", "side", "ordered_quantity", "filled_quantity", "filled_price", "status"] if c in execution_df.columns]
            st.dataframe(execution_df[keep], use_container_width=True, hide_index=True)

        st.caption("모의투자에서도 주문은 사용자 승인 후에만 전송됩니다. 손절·익절은 자동 체결이 아니라 승인 대기 매도요청을 생성합니다.")
    finally:
        service.close()


if __name__ == "__main__":
    run()
