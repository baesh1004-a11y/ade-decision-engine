from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from markets.symbol_display import display_symbol, normalize_ticker
from trading.order_service import TradingOrderService
from trading.scheduled_order_service import ScheduledOrderService


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 예약주문", page_icon="🗓️", layout="wide")
    scheduled = ScheduledOrderService(db_path)
    orders = TradingOrderService(db_path)
    try:
        activated = scheduled.activate_due()
        if activated:
            st.success(f"예약 시각이 도래한 {len(activated)}건을 승인 대기 주문으로 전환했습니다.")

        st.title("예약주문")
        st.caption("예약 시각이 되면 기존 사용자 승인 대기 주문으로 전환됩니다. KIS로 즉시 전송되지 않습니다.")

        recommendations = orders.latest_recommendations(50)
        if not recommendations:
            st.warning("예약주문에 사용할 최신 한국 추천 결과가 없습니다.")
        else:
            labels = [
                f"#{int(row.get('rank_no') or 0)} {display_symbol(row.get('name'), row.get('ticker'), 'kr')}"
                for row in recommendations
            ]
            index = st.selectbox("종목", range(len(recommendations)), format_func=lambda i: labels[i])
            selected = recommendations[index]
            ticker = normalize_ticker(selected["ticker"], "kr")
            label = display_symbol(selected.get("name"), ticker, "kr")

            with st.form(f"scheduled_order_{ticker}"):
                c1, c2, c3 = st.columns(3)
                side_label = c1.selectbox("주문 방향", ["매수", "매도"])
                quantity = c2.number_input("수량", min_value=1, value=1, step=1)
                order_type_label = c3.selectbox("주문 유형", ["시장가", "지정가"])
                limit_price = st.number_input(
                    "지정가 (시장가 선택 시 무시)", min_value=0.0, value=0.0, step=10.0
                )
                target_col, stop_col = st.columns(2)
                target = target_col.number_input(
                    "익절 기준 수익률(%)", value=float(selected.get("target_return") or 0.0), step=0.1
                )
                stop = stop_col.number_input(
                    "손절 기준 수익률(%)", value=float(selected.get("stop_return") or 0.0), step=0.1
                )
                date_col, time_col = st.columns(2)
                scheduled_date = date_col.date_input("예약 날짜")
                scheduled_time = time_col.time_input("예약 시각", value=time(9, 5))
                submitted = st.form_submit_button("예약주문 등록", type="primary", width="stretch")

            if submitted:
                order_type = "MARKET" if order_type_label == "시장가" else "LIMIT"
                if order_type == "LIMIT" and float(limit_price) <= 0:
                    st.error("지정가 주문은 0원보다 큰 가격을 입력해야 합니다.")
                else:
                    scheduled_at = datetime.combine(
                        scheduled_date, scheduled_time, tzinfo=ZoneInfo("Asia/Seoul")
                    )
                    try:
                        schedule_id = scheduled.create_schedule(
                            ticker=ticker,
                            name=selected.get("name"),
                            side="BUY" if side_label == "매수" else "SELL",
                            quantity=int(quantity),
                            scheduled_at=scheduled_at,
                            order_type=order_type,
                            limit_price=None if order_type == "MARKET" else float(limit_price),
                            target_return=float(target),
                            stop_return=float(stop),
                            source_run_id=str(selected.get("run_id") or ""),
                            source_rank=int(selected.get("rank_no") or 0),
                        )
                        st.success(f"예약주문을 등록했습니다: {schedule_id}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"예약주문 등록 실패: {exc}")

        st.markdown("### 예약 대기")
        pending = scheduled.pending_schedules()
        if not pending:
            st.caption("예약 대기 주문이 없습니다.")
        else:
            for row in pending:
                label = display_symbol(row.get("name"), row.get("ticker"), "kr")
                cols = st.columns([2.2, 1, 1, 1.8, 1])
                cols[0].write(f"**{label}**")
                cols[1].write(f"{row['side']} {row['quantity']}주")
                cols[2].write(row["order_type"])
                cols[3].write(_kst_text(row["scheduled_at"]))
                if cols[4].button("예약 취소", key=f"cancel_schedule_{row['schedule_id']}"):
                    try:
                        scheduled.cancel_schedule(str(row["schedule_id"]))
                        st.success("예약주문을 취소했습니다.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"예약 취소 실패: {exc}")

        st.markdown("### 예약주문 이력")
        history = scheduled.list_schedules()
        if not history:
            st.caption("예약주문 이력이 없습니다.")
        else:
            import pandas as pd

            frame = pd.DataFrame(history)
            columns = [
                "schedule_id", "scheduled_at", "ticker", "name", "side", "quantity",
                "order_type", "limit_price", "status", "generated_request_id", "error_message",
            ]
            st.dataframe(frame[[column for column in columns if column in frame.columns]], width="stretch", hide_index=True)
    finally:
        orders.close()
        scheduled.close()


def _kst_text(value: str) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


if __name__ == "__main__":
    run()
