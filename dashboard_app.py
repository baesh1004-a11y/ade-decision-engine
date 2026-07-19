from __future__ import annotations

import streamlit as st


PAGES = {
    "홈": [
        st.Page("ade_home.py", title="Command Center", icon="🏠", default=True),
    ],
    "1. 오늘의 투자": [
        st.Page("pages/14_Recommendation_Workbench.py", title="투자 워크벤치", icon="📊"),
        st.Page("pages/7_Daily_Center.py", title="한국 추천", icon="🇰🇷"),
        st.Page("pages/10_US_Daily_Center.py", title="미국 추천", icon="🇺🇸"),
    ],
    "2. 추천 검토": [
        st.Page("pages/13_Surge_Pattern_Lab.py", title="추천 근거 비교", icon="🔍"),
        st.Page("pages/5_JP_Radar_Live.py", title="AI 레이더", icon="🎯"),
        st.Page("pages/2_Meta_Score.py", title="한국 검증", icon="✅"),
        st.Page("pages/11_US_Meta_Score.py", title="미국 검증", icon="✅"),
    ],
    "3. 주문 실행": [
        st.Page("pages/9_Trading_Desk.py", title="한국 주문", icon="🇰🇷"),
        st.Page("pages/12_US_Trading_Desk.py", title="미국 주문", icon="🇺🇸"),
    ],
    "4. 투자 성과": [
        st.Page("pages/1_ADE_Cockpit.py", title="포트폴리오", icon="💼"),
        st.Page("pages/3_Live_Monitor.py", title="실시간 모니터링", icon="📡"),
        st.Page("pages/6_Feedback.py", title="성과 분석", icon="📈"),
    ],
    "5. 시스템": [
        st.Page("pages/4_KIS_Account.py", title="KIS 계좌", icon="🔐"),
        st.Page("pages/8_Mobile_Access.py", title="모바일", icon="📱"),
    ],
}


def main() -> None:
    navigation = st.navigation(PAGES, position="sidebar", expanded=True)
    navigation.run()


if __name__ == "__main__":
    main()
