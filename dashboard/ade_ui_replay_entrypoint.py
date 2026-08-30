from __future__ import annotations

import time

from broker.kis_websocket import shared_market_client
from dashboard import ade_ui_v1_app as base_app
from dashboard import ade_ui_v1_entrypoint as terminal
from dashboard.kis_zero_base_bridge import kis_configuration_status, probe_kis_connection
from dashboard.order_candidate_store import store_health
from dashboard.overview_workspace_no_charts import render_overview_workspace
from dashboard.replay_target_terminal import render_replay_target_terminal


KIS_PROBE_RESULT_KEY = "ade_kis_probe_result"
KIS_PROBE_AT_KEY = "ade_kis_probe_at"


def _render_overview_without_charts() -> None:
    render_overview_workspace(base_app)


def _render_top_navigation() -> None:
    st = base_app.st
    workspace = base_app.get_workspace(st.session_state.ade_ui_workspace)
    st.markdown(
        f'<div class="ade-top-shell"><div class="ade-brand-block"><div class="ade-brand-mark">ADE</div><div class="ade-brand-copy">Decision Engine · {workspace.short_name}</div></div></div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.0, 1.2, 1.25])
    items = [
        (c1, "상황종합판"),
        (c2, "추천결과"),
        (c3, "주문"),
        (c4, "JP Radar"),
        (c5, "Replay Watch"),
    ]
    for col, label in items:
        if col.button(
            label,
            type="primary" if st.session_state.ade_primary_page == label else "secondary",
            use_container_width=True,
            key=f"nav_{label.replace(' ', '_')}",
        ):
            base_app._navigate_primary(label)


def _render_kis_connection_control() -> None:
    """Keep an explicit KIS REST connection check visible in the main terminal."""

    st = base_app.st
    st.markdown(
        """
        <style>
        .ade-kis-connect-row{display:flex;align-items:center;gap:8px;min-height:42px;padding:4px 2px 8px}
        .ade-kis-dot{width:8px;height:8px;border-radius:999px;background:#94a3b8;display:inline-block;margin-right:7px}
        .ade-kis-dot.ok{background:#16a34a}.ade-kis-dot.fail{background:#dc2626}.ade-kis-dot.wait{background:#d97706}
        .ade-kis-copy{font-size:12px;font-weight:800;color:#475569}.ade-kis-sub{font-size:10px;font-weight:600;color:#94a3b8;margin-left:8px}
        </style>
        """,
        unsafe_allow_html=True,
    )

    config = kis_configuration_status()
    left, right = st.columns([4.6, 1.0])

    with right:
        check = st.button(
            "KIS 연결 확인",
            use_container_width=True,
            key="ade_kis_connection_probe",
            disabled=not bool(config.get("configured")),
        )

    if check:
        with st.spinner("KIS 모의투자 REST 연결과 계좌를 확인하는 중입니다..."):
            result = probe_kis_connection(base_app.get_market_profile("kr").db_path)
        st.session_state[KIS_PROBE_RESULT_KEY] = result
        st.session_state[KIS_PROBE_AT_KEY] = time.time()
        if result.get("rest_ok") and result.get("account_ok"):
            try:
                base_app._cached_kis_snapshot.clear()
            except Exception:
                pass

    result = st.session_state.get(KIS_PROBE_RESULT_KEY)
    checked_at = st.session_state.get(KIS_PROBE_AT_KEY)

    if not config.get("configured"):
        dot_class = "fail"
        headline = "KIS 설정 미완료"
        detail = " · ".join(config.get("missing") or [])
    elif result and result.get("rest_ok") and result.get("account_ok"):
        dot_class = "ok"
        headline = "KIS REST 연결 정상 · PAPER"
        detail = f"계좌 갱신 완료 · 보유 {int(result.get('position_count') or 0)}개"
        if checked_at:
            detail += f" · 확인 {time.strftime('%H:%M:%S', time.localtime(float(checked_at)))}"
    elif result:
        dot_class = "fail"
        headline = "KIS REST 연결 실패"
        detail = str(result.get("error") or "응답을 확인할 수 없습니다.")
    else:
        dot_class = "wait"
        headline = "KIS PAPER 설정됨 · 실제 연결 미확인"
        detail = "오른쪽 버튼을 눌러 REST/계좌 연결을 확인하세요."

    with left:
        st.markdown(
            f'<div class="ade-kis-connect-row"><div class="ade-kis-copy"><span class="ade-kis-dot {dot_class}"></span>{headline}<span class="ade-kis-sub">{detail}</span></div></div>',
            unsafe_allow_html=True,
        )


def _render_status_bar() -> None:
    """Separate KIS configuration, verified REST state, and websocket state."""

    st = base_app.st
    config = kis_configuration_status()
    probe = st.session_state.get(KIS_PROBE_RESULT_KEY)

    if probe and probe.get("rest_ok") and probe.get("account_ok"):
        kis_text, kis_class = "KIS REST OK", "ade-ok"
    elif probe:
        kis_text, kis_class = "KIS REST ERROR", ""
    elif config.get("configured"):
        kis_text, kis_class = "KIS REST CHECK", ""
    else:
        kis_text, kis_class = "KIS OFF", ""

    health = shared_market_client().health_snapshot()
    latest_received_at = health.get("latest_received_at")
    if health.get("connected") and latest_received_at:
        age = time.time() - float(latest_received_at)
        ws_text = "WS LIVE" if age <= 3 else ("WS DELAY" if age <= 10 else "WS STALE")
        ws_class = "ade-ok" if age <= 3 else ""
    elif health.get("connected"):
        ws_text, ws_class = "WS WAIT", ""
    else:
        ws_text, ws_class = "WS OFF", ""

    candidate_health = store_health()
    schema_version = candidate_health.get("schema_version")
    candidate_text = f"DB v{schema_version}" if candidate_health.get("status") == "정상" else "DB ERROR"
    candidate_class = "ade-ok" if candidate_health.get("status") == "정상" else ""
    st.markdown(
        f'<div class="ade-statusbar"><span>ADE TERMINAL</span><span class="{kis_class}">{kis_text}</span><span class="{ws_class}">{ws_text}</span><span class="{candidate_class}">{candidate_text}</span><span>REPLAY / STO READY</span></div>',
        unsafe_allow_html=True,
    )


def run() -> None:
    st = base_app.st
    st.set_page_config(
        page_title="ADE Decision Engine",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    base_app._apply_zero_base_theme()
    base_app._init_state()
    base_app._apply_workspace_theme()

    base_app._render_overview = _render_overview_without_charts
    base_app._render_status_bar = _render_status_bar
    base_app._render_orders = terminal._render_orders
    base_app._render_recommendations = terminal._render_recommendations
    base_app._render_recommendation_detail = terminal._render_recommendation_detail

    _render_top_navigation()
    _render_kis_connection_control()
    page = st.session_state.ade_primary_page

    if page == "상황종합판":
        base_app._release_live_lease()
        base_app._render_overview()
    elif page == "추천결과":
        base_app._release_live_lease()
        base_app._render_recommendations()
    elif page == "주문":
        base_app._render_orders()
    elif page == "JP Radar":
        base_app._release_live_lease()
        base_app._render_jp_radar()
    elif page == "Replay Watch":
        base_app._release_live_lease()
        render_replay_target_terminal()
    else:
        st.session_state.ade_primary_page = "상황종합판"
        st.rerun()

    base_app._render_status_bar()


if __name__ == "__main__":
    run()
