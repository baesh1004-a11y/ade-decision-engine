from __future__ import annotations

import streamlit as st


# 업무 흐름을 그대로 따라가도록 메뉴를 구성한다.
# 추천 생성 → 유사 패턴 확인 → 종합 판단 → 주문 → 성과 확인
PAGES = {
    "홈": [
        st.Page("ade_home.py", title="종합 상황판", icon="🏠", default=True),
    ],
    "1. 추천 생성": [
        st.Page("pages/7_Daily_Center.py", title="한국 추천종목", icon="🇰🇷"),
        st.Page("pages/10_US_Daily_Center.py", title="미국 추천종목", icon="🇺🇸"),
    ],
    "2. 분석 및 판단": [
        st.Page("pages/13_Surge_Pattern_Lab.py", title="급등 패턴 비교", icon="📈"),
        st.Page("pages/2_Meta_Score.py", title="한국 종합판단", icon="🧠"),
        st.Page("pages/11_US_Meta_Score.py", title="미국 종합판단", icon="📊"),
        st.Page("pages/5_JP_Radar_Live.py", title="AI 레이더", icon="🎯"),
    ],
    "3. 주문 실행": [
        st.Page("pages/9_Trading_Desk.py", title="한국 주문관리", icon="💳"),
        st.Page("pages/12_US_Trading_Desk.py", title="미국 주문관리", icon="💵"),
    ],
    "4. 보유 및 성과": [
        st.Page("pages/1_ADE_Cockpit.py", title="포트폴리오 현황", icon="🖥️"),
        st.Page("pages/3_Live_Monitor.py", title="실시간 모니터링", icon="📡"),
        st.Page("pages/6_Feedback.py", title="성과 분석", icon="📋"),
    ],
    "시스템": [
        st.Page("pages/4_KIS_Account.py", title="KIS 계좌", icon="🏦"),
        st.Page("pages/8_Mobile_Access.py", title="모바일 접속", icon="📱"),
    ],
}


def main() -> None:
    navigation = st.navigation(PAGES, position="sidebar", expanded=True)
    navigation.run()


if __name__ == "__main__":
    main()
