from __future__ import annotations

from dashboard import ade_ui_v1_app as base_app
from dashboard import ade_ui_v1_entrypoint as terminal
from dashboard.replay_target_terminal import render_replay_target_terminal


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

    # Keep the current production renderers and add Replay Watch as a fifth,
    # isolated primary workspace.
    base_app._render_overview = terminal._render_overview
    base_app._render_status_bar = terminal._render_status_bar
    base_app._render_orders = terminal._render_orders
    base_app._render_recommendations = terminal._render_recommendations
    base_app._render_recommendation_detail = terminal._render_recommendation_detail

    _render_top_navigation()
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
