from __future__ import annotations

import streamlit as st

from dashboard.design_system import apply_design_system


NAVIGATION = {
    "홈": [
        st.Page("ade_home.py", title="ADE 대시보드", icon="🏠", default=True),
    ],
    "오늘의 투자": [
        st.Page("pages/14_Recommendation_Workbench.py", title="추천종목 분석", icon="📊"),
        st.Page("pages/7_Daily_Center.py", title="국내 일일 분석", icon="🇰🇷"),
        st.Page("pages/10_US_Daily_Center.py", title="미국 일일 분석", icon="🇺🇸"),
    ],
    "분석·검증": [
        st.Page("pages/13_Surge_Pattern_Lab.py", title="급등 패턴 연구소", icon="🔍"),
        st.Page("pages/2_Meta_Score.py", title="국내 메타 스코어", icon="✅"),
        st.Page("pages/11_US_Meta_Score.py", title="미국 메타 스코어", icon="✅"),
        st.Page("pages/5_JP_Radar_Live.py", title="급등주 실시간 탐지", icon="🎯"),
    ],
    "트레이딩": [
        st.Page("pages/9_Trading_Desk.py", title="국내 트레이딩", icon="🇰🇷"),
        st.Page("pages/12_US_Trading_Desk.py", title="미국 트레이딩", icon="🇺🇸"),
        st.Page("pages/15_Scheduled_Orders.py", title="예약 주문", icon="🗓️"),
    ],
    "모니터링·성과": [
        st.Page("pages/1_ADE_Cockpit.py", title="ADE 통합관제", icon="💼"),
        st.Page("pages/3_Live_Monitor.py", title="실시간 모니터", icon="📡"),
        st.Page("pages/6_Feedback.py", title="성과 분석", icon="📈"),
    ],
    "시스템": [
        st.Page("pages/4_KIS_Account.py", title="KIS 계좌", icon="🔐"),
        st.Page("pages/8_Mobile_Access.py", title="모바일 접속", icon="📱"),
    ],
}

MOBILE_NAV_LINKS = (
    ("/", "🏠", "홈"),
    ("/Recommendation_Workbench", "📊", "추천"),
    ("/Trading_Desk", "💳", "트레이딩"),
    ("/Scheduled_Orders", "🗓️", "예약"),
    ("/ADE_Cockpit", "💼", "성과"),
)


def _mobile_nav_html() -> str:
    links = "".join(
        f'<a href="{href}" target="_self"><span>{icon}</span><span>{label}</span></a>'
        for href, icon, label in MOBILE_NAV_LINKS
    )
    return f'<nav class="ade-mobile-top-nav" aria-label="모바일 빠른 메뉴">{links}</nav>'


def main() -> None:
    apply_design_system()
    navigation = st.navigation(
        NAVIGATION,
        position="sidebar",
        expanded=False,
    )
    navigation.run()
    st.markdown(_mobile_nav_html(), unsafe_allow_html=True)


if __name__ == "__main__":
    main()
