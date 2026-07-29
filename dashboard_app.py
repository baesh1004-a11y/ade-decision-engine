from __future__ import annotations

import streamlit as st

from dashboard.design_system import apply_design_system


PAGES = {
    "홈": [
        st.Page("ade_home.py", title="상황판", icon="🏠", default=True),
    ],
    "1. 오늘의 투자": [
        st.Page("pages/14_Recommendation_Workbench.py", title="추천 워크벤치", icon="📊"),
        st.Page("pages/7_Daily_Center.py", title="한국 추천", icon="🇰🇷"),
        st.Page("pages/10_US_Daily_Center.py", title="미국 추천", icon="🇺🇸"),
    ],
    "2. 분석 · 검증": [
        st.Page("pages/13_Surge_Pattern_Lab.py", title="급등 패턴 분석", icon="🔍"),
        st.Page("pages/2_Meta_Score.py", title="한국 검증 이력", icon="✅"),
        st.Page("pages/11_US_Meta_Score.py", title="미국 검증 이력", icon="✅"),
        st.Page("pages/5_JP_Radar_Live.py", title="AI 실시간 레이더", icon="🎯"),
    ],
    "3. 주문 실행": [
        st.Page("pages/9_Trading_Desk.py", title="한국 주문", icon="🇰🇷"),
        st.Page("pages/12_US_Trading_Desk.py", title="미국 주문", icon="🇺🇸"),
        st.Page("pages/15_Scheduled_Orders.py", title="예약 주문", icon="🗓️"),
    ],
    "4. 투자 성과": [
        st.Page("pages/1_ADE_Cockpit.py", title="포트폴리오", icon="💼"),
        st.Page("pages/3_Live_Monitor.py", title="실시간 모니터링", icon="📡"),
        st.Page("pages/6_Feedback.py", title="성과 분석", icon="📈"),
    ],
    "5. 시스템": [
        st.Page("pages/4_KIS_Account.py", title="KIS 계좌", icon="🔐"),
        st.Page("pages/8_Mobile_Access.py", title="모바일 접속", icon="📱"),
    ],
}

MOBILE_NAV_LINKS = (
    ("/", "🏠", "홈"),
    ("/Recommendation_Workbench", "📊", "추천"),
    ("/Trading_Desk", "💳", "주문"),
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
        PAGES,
        position="sidebar",
        expanded=False,
    )
    navigation.run()
    st.markdown(_mobile_nav_html(), unsafe_allow_html=True)


if __name__ == "__main__":
    main()
