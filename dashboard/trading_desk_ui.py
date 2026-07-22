from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


STATUS_META = {
    "FILLED": ("✓", "완료", "green"),
    "DONE": ("✓", "완료", "green"),
    "PARTIAL": ("↻", "부분 체결", "blue"),
    "SENT": ("↻", "전송됨", "blue"),
    "SENDING": ("↻", "전송 중", "blue"),
    "PENDING_APPROVAL": ("▲", "승인 대기", "orange"),
    "VERIFY_REQUIRED": ("▲", "확인 필요", "orange"),
    "REJECTED": ("■", "거절", "red"),
    "FAILED": ("■", "오류", "red"),
    "CANCELLED": ("—", "취소", "gray"),
    "EXPIRED": ("—", "만료", "gray"),
}


def status_text(status: object) -> str:
    raw = str(status or "UNKNOWN").upper()
    icon, label, _color = STATUS_META.get(raw, ("—", raw, "gray"))
    return f"{icon} {label}"


def render_view_mode(st, service, *, market: str) -> str:
    preference_key = f"{market}_trading_view_mode"
    state_key = f"{preference_key}_widget"
    stored = service.dashboard_preference(preference_key, "기본 보기")
    if stored not in ("기본 보기", "상세 보기"):
        stored = "기본 보기"
    st.session_state.setdefault(state_key, stored)
    selected = st.segmented_control(
        "표시 정보", ["기본 보기", "상세 보기"], key=state_key,
        label_visibility="collapsed", width="content",
    ) or "기본 보기"
    if selected != stored:
        service.set_dashboard_preference(preference_key, selected)
    return selected


def render_empty_state(st, title: str, description: str, *, icon: str = ":material/info:") -> None:
    with st.container(border=True, horizontal_alignment="center"):
        st.subheader(title, text_alignment="center")
        st.caption(description, text_alignment="center")
        st.markdown(icon, text_alignment="center")


def render_order_timeline(st, order: dict, executions: list[dict], *, time_formatter) -> None:
    status = str(order.get("status") or "UNKNOWN").upper()
    events: list[tuple[str, str, str]] = []
    if _present(order.get("created_at")):
        events.append((time_formatter(order["created_at"]), "주문 요청 생성", "✓"))
    if _present(order.get("approved_at")):
        events.append((time_formatter(order["approved_at"]), "사용자 승인", "✓"))
    if _present(order.get("sent_at")):
        events.append((time_formatter(order["sent_at"]), "KIS 전송", "✓"))
    for event in reversed(executions):
        filled = int(event.get("filled_quantity") or 0)
        ordered = int(event.get("ordered_quantity") or order.get("quantity") or 0)
        label = f"{filled}/{ordered}주 체결 · {status_text(event.get('status'))}"
        events.append((time_formatter(event.get("captured_at")), label, "↻" if filled < ordered else "✓"))
    if not events:
        st.caption("표시할 주문 진행 이력이 없습니다.")
        return
    with st.container(border=True):
        st.markdown(f"**{order.get('ticker', '-')} · {status_text(status)}**")
        for timestamp, label, marker in events:
            st.markdown(f"`{timestamp}`  {marker} **{label}**")


def _present(value: object) -> bool:
    return value is not None and str(value).strip().lower() not in ("", "nan", "nat", "none")


def render_mobile_bottom_nav(st, *, pending_count: int, state_key: str) -> None:
    st.session_state.setdefault(state_key, "차트")

    def select(value: str) -> None:
        st.session_state[state_key] = value

    with st.bottom:
        with st.container(horizontal=True, horizontal_alignment="distribute"):
            st.button("추천", icon=":material/format_list_bulleted:", on_click=select, args=("추천",), key=f"{state_key}_rec")
            st.button("차트", icon=":material/candlestick_chart:", on_click=select, args=("차트",), key=f"{state_key}_chart")
            st.button("분석", icon=":material/analytics:", on_click=select, args=("분석",), key=f"{state_key}_analysis")
            st.button("주문", icon=":material/receipt_long:", on_click=select, args=("주문",), key=f"{state_key}_order")
            st.button(
                f"승인 {pending_count}" if pending_count else "승인",
                icon=":material/pending_actions:", on_click=select, args=("승인",), key=f"{state_key}_pending",
            )
