from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import streamlit as st


@dataclass(frozen=True)
class OrderContext:
    market: str
    ticker: str
    name: str
    current_price: float
    change_rate: float
    cash: float
    holding_quantity: int
    orderable_quantity: int


def _money(value: float) -> str:
    return f"₩{value:,.0f}"


def _scheduled_db_path() -> Path:
    path = Path("datahub/scheduled_orders.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_scheduled_schema() -> None:
    with sqlite3.connect(_scheduled_db_path()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                limit_price REAL,
                trigger_type TEXT NOT NULL,
                trigger_price REAL,
                execute_at TEXT,
                recurrence TEXT NOT NULL DEFAULT 'ONCE',
                status TEXT NOT NULL DEFAULT 'PENDING',
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            )
            """
        )
        conn.commit()


def load_scheduled_orders() -> list[dict[str, Any]]:
    _ensure_scheduled_schema()
    with sqlite3.connect(_scheduled_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM scheduled_orders ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def cancel_scheduled_order(order_id: int) -> None:
    _ensure_scheduled_schema()
    with sqlite3.connect(_scheduled_db_path()) as conn:
        conn.execute("UPDATE scheduled_orders SET status='CANCELLED' WHERE id=?", (int(order_id),))
        conn.commit()


def save_scheduled_order(payload: dict[str, Any]) -> int:
    _ensure_scheduled_schema()
    with sqlite3.connect(_scheduled_db_path()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO scheduled_orders(
                market, ticker, name, side, order_type, quantity, limit_price,
                trigger_type, trigger_price, execute_at, recurrence, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            (
                payload["market"],
                payload["ticker"],
                payload.get("name"),
                payload["side"],
                payload["order_type"],
                int(payload["quantity"]),
                payload.get("limit_price"),
                payload["trigger_type"],
                payload.get("trigger_price"),
                payload.get("execute_at"),
                payload.get("recurrence", "ONCE"),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def render_search_launcher(
    *,
    market: str,
    search_func: Callable[[str, str, int], list[dict[str, str]]],
    on_open: Callable[[str, str], None],
    on_add_candidate: Callable[[str, str], None],
) -> None:
    st.markdown("### 종목 검색")
    st.caption("종목명 또는 종목코드를 입력하고 검색 결과에서 바로 주문을 선택하세요.")
    query = st.text_input(
        "종목명 또는 종목코드",
        placeholder="예: 삼성전자 또는 005930",
        key=f"standard_order_search_{market}",
    )
    if not query:
        return
    matches = search_func(market, query, 10)
    if not matches:
        st.warning("일치하는 종목을 찾지 못했습니다. 종목명 또는 종목코드를 다시 확인하세요.")
        return
    for row in matches:
        c1, c2, c3 = st.columns([4, 1, 1])
        c1.markdown(f"**{row['symbol']}**  \n`{row['ticker']}`")
        if c2.button("바로 주문", key=f"open_{market}_{row['ticker']}", type="primary", use_container_width=True):
            on_open(row["ticker"], row["symbol"])
        if c3.button("후보 저장", key=f"save_{market}_{row['ticker']}", use_container_width=True):
            on_add_candidate(row["ticker"], row["symbol"])


def render_order_ticket(
    *,
    context: OrderContext,
    submit_callback: Callable[[str, str, int, str, float | None], tuple[bool, str]],
) -> None:
    st.markdown(f"## {context.name} · {context.ticker}")
    summary = st.columns(5)
    summary[0].metric("현재가", _money(context.current_price))
    summary[1].metric("등락률", f"{context.change_rate:+.2f}%")
    summary[2].metric("주문가능 현금", _money(context.cash))
    summary[3].metric("보유수량", f"{context.holding_quantity:,}주")
    summary[4].metric("최대 주문가능", f"{context.orderable_quantity:,}주")

    st.markdown("### 1. 주문 방향")
    side = st.segmented_control(
        "주문 방향",
        options=["매수", "매도"],
        default="매수",
        key=f"std_side_{context.ticker}",
        label_visibility="collapsed",
    ) or "매수"

    st.markdown("### 2. 주문 방식")
    order_label = st.segmented_control(
        "주문 방식",
        options=["시장가", "지정가"],
        default="지정가",
        key=f"std_type_{context.ticker}",
        label_visibility="collapsed",
    ) or "지정가"
    order_type = "MARKET" if order_label == "시장가" else "LIMIT"
    price = None
    if order_type == "LIMIT":
        price = st.number_input(
            "지정가",
            min_value=0.0,
            value=float(context.current_price),
            step=100.0,
            key=f"std_price_{context.ticker}_{side}",
        )
    else:
        st.info("시장가는 현재가와 다른 가격으로 체결될 수 있습니다.")

    st.markdown("### 3. 수량")
    available = context.orderable_quantity if side == "매수" else context.holding_quantity
    quantity_key = f"std_qty_{context.ticker}_{side}"
    st.session_state.setdefault(quantity_key, 1 if available > 0 else 0)
    quick = st.columns(5)
    presets = [("1주", 1), ("10주", 10), ("25%", max(1, available // 4)), ("50%", max(1, available // 2)), ("최대", available)]
    for col, (label, value) in zip(quick, presets):
        if col.button(label, key=f"qty_{context.ticker}_{side}_{label}", use_container_width=True, disabled=available <= 0):
            st.session_state[quantity_key] = min(max(0, int(value)), available)
            st.rerun()
    quantity = st.number_input(
        "주문 수량",
        min_value=0,
        max_value=max(0, available),
        step=1,
        key=quantity_key,
    )

    reference = float(price if price is not None else context.current_price)
    estimated = reference * int(quantity)
    st.markdown("### 4. 주문 확인")
    with st.container(border=True):
        review = pd.DataFrame(
            [
                {"항목": "종목", "내용": f"{context.name} · {context.ticker}"},
                {"항목": "구분", "내용": side},
                {"항목": "주문방식", "내용": order_label},
                {"항목": "가격", "내용": "시장가" if price is None else _money(float(price))},
                {"항목": "수량", "내용": f"{int(quantity):,}주"},
                {"항목": "예상금액", "내용": _money(estimated)},
            ]
        )
        st.dataframe(review, hide_index=True, use_container_width=True)
        confirmed = st.checkbox("주문 내용을 확인했습니다.", key=f"std_confirm_{context.ticker}_{side}_{order_type}")
        disabled = not confirmed or quantity <= 0 or quantity > available
        if st.button(
            f"{side} 주문 전송",
            type="primary",
            use_container_width=True,
            disabled=disabled,
            key=f"std_submit_{context.ticker}_{side}_{order_type}",
        ):
            ok, message = submit_callback(context.ticker, side, int(quantity), order_type, float(price) if price is not None else None)
            if ok:
                st.success(message)
            else:
                st.error(message)

    with st.expander("실시간 호가 및 상세 시세", expanded=False):
        st.caption("실시간 10호가, 체결강도, PER/PBR 등 상세정보는 보조정보로 제공합니다.")


def render_scheduled_order_tab(*, market: str, ticker: str | None = None, name: str | None = None, current_price: float = 0.0) -> None:
    st.markdown("### 예약주문")
    st.caption("예약주문은 조건 충족 시 즉시 전송하지 않고 승인 대기 상태로 전환하는 표준 흐름을 전제로 저장합니다.")
    if not ticker:
        st.info("먼저 주문할 종목을 선택하세요.")
    else:
        c1, c2 = st.columns(2)
        side = c1.selectbox("구분", ["매수", "매도"], key=f"sched_side_{ticker}")
        order_label = c2.selectbox("주문방식", ["지정가", "시장가"], key=f"sched_type_{ticker}")
        order_type = "LIMIT" if order_label == "지정가" else "MARKET"
        quantity = st.number_input("수량", min_value=1, value=1, step=1, key=f"sched_qty_{ticker}")
        limit_price = None
        if order_type == "LIMIT":
            limit_price = st.number_input("주문가격", min_value=0.0, value=float(current_price or 0), step=100.0, key=f"sched_limit_{ticker}")
        trigger_label = st.selectbox("실행 조건", ["지정 시각", "현재가 이하", "현재가 이상"], key=f"sched_trigger_{ticker}")
        recurrence_label = st.selectbox("반복", ["일회", "매일", "매주", "매월"], key=f"sched_repeat_{ticker}")
        trigger_map = {"지정 시각": "TIME", "현재가 이하": "PRICE_BELOW", "현재가 이상": "PRICE_ABOVE"}
        repeat_map = {"일회": "ONCE", "매일": "DAILY", "매주": "WEEKLY", "매월": "MONTHLY"}
        execute_at = None
        trigger_price = None
        if trigger_label == "지정 시각":
            run_date = st.date_input("실행일", value=date.today(), key=f"sched_date_{ticker}")
            run_time = st.time_input("실행시각", value=dt_time(9, 0), key=f"sched_time_{ticker}")
            execute_at = datetime.combine(run_date, run_time).isoformat()
        else:
            trigger_price = st.number_input("조건가격", min_value=0.0, value=float(current_price or 0), step=100.0, key=f"sched_trigger_price_{ticker}")
        if st.button("예약주문 저장", type="primary", use_container_width=True, key=f"sched_save_{ticker}"):
            order_id = save_scheduled_order(
                {
                    "market": market,
                    "ticker": ticker,
                    "name": name or ticker,
                    "side": side,
                    "order_type": order_type,
                    "quantity": int(quantity),
                    "limit_price": limit_price,
                    "trigger_type": trigger_map[trigger_label],
                    "trigger_price": trigger_price,
                    "execute_at": execute_at,
                    "recurrence": repeat_map[recurrence_label],
                }
            )
            st.success(f"예약주문 #{order_id}가 저장되었습니다.")

    rows = load_scheduled_orders()
    if not rows:
        st.info("저장된 예약주문이 없습니다.")
        return
    frame = pd.DataFrame(rows)
    shown = frame[[column for column in ["id", "name", "ticker", "side", "order_type", "quantity", "limit_price", "trigger_type", "trigger_price", "execute_at", "recurrence", "status", "retry_count", "last_error"] if column in frame.columns]]
    st.dataframe(shown, hide_index=True, use_container_width=True)
    cancellable = [int(row["id"]) for row in rows if row.get("status") == "PENDING"]
    if cancellable:
        selected = st.selectbox("취소할 예약주문", cancellable, key="scheduled_cancel_id")
        if st.button("선택 예약주문 취소", use_container_width=True):
            cancel_scheduled_order(int(selected))
            st.rerun()
