from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

from dashboard.design_system import StatusBadge, apply_design_system, page_header, section
from markets.symbol_display import display_symbol, normalize_ticker
from trading.order_service import TradingOrderService
from trading.scheduled_order_service import ScheduledOrderService


TRIGGER_LABELS = {
    "시간 도래": "TIME",
    "현재가 이하": "PRICE_LE",
    "현재가 이상": "PRICE_GE",
}
RECURRENCE_LABELS = {
    "반복 없음": "NONE",
    "매일": "DAILY",
    "매주": "WEEKLY",
    "매월": "MONTHLY",
}
STATUS_LABELS = {
    "PENDING": "대기",
    "ACTIVE": "감시 중",
    "ACTIVATED": "승인 대기 전환",
    "FAILED": "실패",
    "CANCELLED": "취소",
    "COMPLETED": "완료",
}
SIDE_LABELS = {"BUY": "매수", "SELL": "매도"}
ORDER_TYPE_LABELS = {"MARKET": "시장가", "LIMIT": "지정가"}
RECURRENCE_VALUE_LABELS = {value: label for label, value in RECURRENCE_LABELS.items()}


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 예약 주문", page_icon="🗓️", layout="wide")
    apply_design_system()

    scheduled = ScheduledOrderService(db_path)
    orders = TradingOrderService(db_path)
    try:
        try:
            activated = scheduled.activate_due()
        except Exception as exc:
            activated = []
            st.warning(f"가격 조건 감시 일부를 실행하지 못했습니다: {exc}")
        if activated:
            st.success(f"조건을 충족한 {len(activated)}건을 승인 대기 주문으로 전환했습니다.")

        pending_snapshot = scheduled.pending_schedules()
        failed_snapshot = [row for row in scheduled.list_schedules() if row.get("status") == "FAILED"]
        page_header(
            "예약 주문",
            "시간 또는 가격 조건이 충족되면 승인 대기 주문으로 전환합니다. KIS로 직접 전송하지 않습니다.",
            eyebrow="ADE · 예약 주문 관리",
            badges=(
                StatusBadge(f"대기 {len(pending_snapshot)}건", "info"),
                StatusBadge(f"실패 {len(failed_snapshot)}건", "warning" if failed_snapshot else "success"),
            ),
        )

        recommendations = orders.latest_recommendations(50)
        section("예약 주문 등록", "시장과 종목, 주문 조건, 실행 조건을 설정합니다.")
        market_label = st.radio("시장", ["한국", "미국"], horizontal=True)
        market = "kr" if market_label == "한국" else "us"

        selected = None
        ticker = ""
        name = ""
        source_run_id = None
        source_rank = None
        if market == "kr" and recommendations:
            labels = [
                f"#{int(row.get('rank_no') or 0)} {display_symbol(row.get('name'), row.get('ticker'), 'kr')}"
                for row in recommendations
            ]
            index = st.selectbox("추천 종목", range(len(recommendations)), format_func=lambda i: labels[i])
            selected = recommendations[index]
            ticker = normalize_ticker(selected["ticker"], "kr")
            name = str(selected.get("name") or ticker)
            source_run_id = str(selected.get("run_id") or "")
            source_rank = int(selected.get("rank_no") or 0)
        else:
            if market == "kr" and not recommendations:
                st.info("최신 추천 결과가 없어 종목을 직접 입력합니다.")
            c1, c2 = st.columns(2)
            ticker = c1.text_input("종목코드", placeholder="예: 005930 또는 AAPL").strip().upper()
            name = c2.text_input("종목명", placeholder="선택 입력").strip() or ticker

        with st.form("scheduled_order_form"):
            c1, c2, c3 = st.columns(3)
            side_label = c1.selectbox("주문 방향", ["매수", "매도"])
            quantity = c2.number_input("수량", min_value=1, value=1, step=1)
            order_type_label = c3.selectbox("주문 유형", ["시장가", "지정가"])
            limit_price = st.number_input("지정가", min_value=0.0, value=0.0, step=1.0, help="시장가 주문에서는 사용하지 않습니다.")

            target_col, stop_col = st.columns(2)
            target_default = float(selected.get("target_return") or 0.0) if selected else 0.0
            stop_default = float(selected.get("stop_return") or 0.0) if selected else 0.0
            target = target_col.number_input("익절 기준 수익률(%)", value=target_default, step=0.1)
            stop = stop_col.number_input("손절 기준 수익률(%)", value=stop_default, step=0.1)

            trigger_label = st.selectbox("예약 조건", list(TRIGGER_LABELS))
            trigger_type = TRIGGER_LABELS[trigger_label]
            trigger_price = None
            scheduled_at = None
            if trigger_type == "TIME":
                date_col, time_col = st.columns(2)
                scheduled_date = date_col.date_input("예약 날짜")
                scheduled_time = time_col.time_input("예약 시각", value=time(9, 5))
                scheduled_at = datetime.combine(scheduled_date, scheduled_time, tzinfo=ZoneInfo("Asia/Seoul"))
            else:
                p1, p2, p3 = st.columns(3)
                trigger_price = p1.number_input("기준 가격", min_value=0.0, value=0.0, step=1.0)
                start_date = p2.date_input("감시 시작 날짜")
                start_time = p3.time_input("감시 시작 시각", value=time(9, 0))
                scheduled_at = datetime.combine(start_date, start_time, tzinfo=ZoneInfo("Asia/Seoul"))

            recurrence_label = st.selectbox("반복", list(RECURRENCE_LABELS))
            recurrence = RECURRENCE_LABELS[recurrence_label]
            recurrence_end_at = None
            max_activations = None
            if recurrence != "NONE":
                r1, r2 = st.columns(2)
                recurrence_end_date = r1.date_input("반복 종료 날짜")
                max_activations = int(r2.number_input("최대 실행 횟수", min_value=1, value=10, step=1))
                recurrence_end_at = datetime.combine(
                    recurrence_end_date,
                    time(23, 59),
                    tzinfo=ZoneInfo("Asia/Seoul"),
                )

            max_retries = int(st.number_input("실패 재시도 횟수", min_value=0, value=3, step=1))
            submitted = st.form_submit_button("예약 주문 등록", type="primary", width="stretch")

        if submitted:
            order_type = "MARKET" if order_type_label == "시장가" else "LIMIT"
            if not ticker:
                st.error("종목코드를 입력해야 합니다.")
            elif order_type == "LIMIT" and float(limit_price) <= 0:
                st.error("지정가 주문은 0보다 큰 가격을 입력해야 합니다.")
            elif trigger_type != "TIME" and float(trigger_price or 0) <= 0:
                st.error("가격 조건 예약은 0보다 큰 기준 가격이 필요합니다.")
            else:
                try:
                    schedule_id = scheduled.create_schedule(
                        ticker=normalize_ticker(ticker, market),
                        name=name,
                        side="BUY" if side_label == "매수" else "SELL",
                        quantity=int(quantity),
                        scheduled_at=scheduled_at,
                        order_type=order_type,
                        limit_price=None if order_type == "MARKET" else float(limit_price),
                        target_return=float(target),
                        stop_return=float(stop),
                        source_run_id=source_run_id,
                        source_rank=source_rank,
                        market=market,
                        trigger_type=trigger_type,
                        trigger_price=float(trigger_price) if trigger_price is not None else None,
                        recurrence=recurrence,
                        recurrence_end_at=recurrence_end_at,
                        max_activations=max_activations,
                        max_retries=max_retries,
                    )
                    st.success(f"예약 주문을 등록했습니다: {schedule_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"예약 주문 등록 실패: {exc}")

        section("예약 대기", "조건 충족 여부를 감시 중인 주문입니다.")
        pending = scheduled.pending_schedules()
        if not pending:
            st.info("예약 대기 주문이 없습니다.")
        else:
            for row in pending:
                label = display_symbol(row.get("name"), row.get("ticker"), str(row.get("market") or "kr"))
                trigger = _trigger_text(row)
                cols = st.columns([2.2, 1.1, 1.3, 2.3, 1, 1])
                cols[0].write(f"**{label}**")
                cols[1].write(f"{SIDE_LABELS.get(str(row['side']), row['side'])} {row['quantity']}주")
                cols[2].write(
                    f"{ORDER_TYPE_LABELS.get(str(row['order_type']), row['order_type'])} · "
                    f"{RECURRENCE_VALUE_LABELS.get(str(row.get('recurrence') or 'NONE'), row.get('recurrence') or 'NONE')}"
                )
                cols[3].write(trigger)
                if cols[4].button("조건 확인", key=f"run_schedule_{row['schedule_id']}"):
                    try:
                        result = scheduled.activate_due()
                        st.success(f"조건 충족 예약 {len(result)}건을 처리했습니다.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"예약 처리 실패: {exc}")
                if cols[5].button("취소", key=f"cancel_schedule_{row['schedule_id']}"):
                    try:
                        scheduled.cancel_schedule(str(row["schedule_id"]))
                        st.success("예약 주문을 취소했습니다.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"예약 취소 실패: {exc}")

        section("실패 예약", "오류로 중단된 예약을 확인하고 재시도합니다.")
        failed = [row for row in scheduled.list_schedules() if row.get("status") == "FAILED"]
        if not failed:
            st.info("실패한 예약 주문이 없습니다.")
        else:
            for row in failed:
                cols = st.columns([2, 3, 1])
                cols[0].write(
                    f"**{row['ticker']} · {SIDE_LABELS.get(str(row['side']), row['side'])} {row['quantity']}주**"
                )
                cols[1].write(str(row.get("error_message") or "-"))
                if cols[2].button("재시도", key=f"retry_schedule_{row['schedule_id']}"):
                    try:
                        scheduled.retry_schedule(str(row["schedule_id"]))
                        st.success("예약을 재시도 대기 상태로 변경했습니다.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"재시도 실패: {exc}")

        section("예약 주문 이력", "등록·실행·실패·취소된 전체 이력입니다.")
        history = scheduled.list_schedules()
        if not history:
            st.info("예약 주문 이력이 없습니다.")
        else:
            frame = pd.DataFrame(history)
            columns = [
                "schedule_id",
                "market",
                "trigger_type",
                "trigger_price",
                "scheduled_at",
                "ticker",
                "name",
                "side",
                "quantity",
                "order_type",
                "limit_price",
                "recurrence",
                "activation_count",
                "status",
                "generated_request_id",
                "retry_count",
                "error_message",
            ]
            shown = frame[[column for column in columns if column in frame.columns]].copy()
            if "market" in shown.columns:
                shown["market"] = shown["market"].map({"kr": "한국", "us": "미국"}).fillna(shown["market"])
            if "side" in shown.columns:
                shown["side"] = shown["side"].map(SIDE_LABELS).fillna(shown["side"])
            if "order_type" in shown.columns:
                shown["order_type"] = shown["order_type"].map(ORDER_TYPE_LABELS).fillna(shown["order_type"])
            if "recurrence" in shown.columns:
                shown["recurrence"] = shown["recurrence"].map(RECURRENCE_VALUE_LABELS).fillna(shown["recurrence"])
            if "status" in shown.columns:
                shown["status"] = shown["status"].map(STATUS_LABELS).fillna(shown["status"])
            shown = shown.rename(
                columns={
                    "schedule_id": "예약번호",
                    "market": "시장",
                    "trigger_type": "예약 조건",
                    "trigger_price": "기준 가격",
                    "scheduled_at": "예약·감시 시작 시각",
                    "ticker": "종목코드",
                    "name": "종목명",
                    "side": "방향",
                    "quantity": "수량",
                    "order_type": "주문 유형",
                    "limit_price": "지정가",
                    "recurrence": "반복",
                    "activation_count": "실행 횟수",
                    "status": "상태",
                    "generated_request_id": "생성 주문번호",
                    "retry_count": "재시도 횟수",
                    "error_message": "오류 메시지",
                }
            )
            st.dataframe(shown, width="stretch", hide_index=True)
    finally:
        orders.close()
        scheduled.close()


def _trigger_text(row: dict) -> str:
    trigger_type = str(row.get("trigger_type") or "TIME")
    if trigger_type == "TIME":
        return _kst_text(row.get("scheduled_at"))
    op = "이하" if trigger_type == "PRICE_LE" else "이상"
    start = _kst_text(row.get("scheduled_at")) if row.get("scheduled_at") else "즉시 감시"
    return f"{float(row.get('trigger_price') or 0):,.2f} {op} · {start}"


def _kst_text(value) -> str:
    if not value:
        return "-"
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


if __name__ == "__main__":
    run()
