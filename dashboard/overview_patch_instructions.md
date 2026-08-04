# ADE 상황종합판 통합 패치

`dashboard/ade_ui_v1_app.py`에 다음 두 변경을 적용한다.

## 1. import 추가

```python
from dashboard.overview_market_panel import render_market_overview_panel
```

## 2. 상황종합판 함수 교체

```python
def _render_overview() -> None:
    tabs = st.segmented_control(
        "상황종합판 하위 메뉴",
        options=["시장", "내 투자"],
        default="시장" if st.session_state.ade_overview_tab not in {"시장", "내 투자"} else st.session_state.ade_overview_tab,
        key="ade_overview_segment",
        label_visibility="collapsed",
    )
    st.session_state.ade_overview_tab = tabs or "시장"
    if tabs == "시장":
        _render_market_overview()
    else:
        _render_portfolio_overview()


def _render_market_overview() -> None:
    render_market_overview_panel()
```

기존 `_render_event_timeline` 함수와 이벤트 탭 분기는 삭제한다.

## 3. WebSocket 상태 문구 교체

`_render_status_bar()`에서 연결되지 않았고 구독도 없는 경우:

```python
ws_text, ws_class = "실시간 미사용 · 주문 화면에서 종목 선택 시 연결", ""
```

연결 상태 로직 자체는 유지한다.
