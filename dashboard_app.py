from __future__ import annotations

import streamlit as st


PAGES = {
    "홈": [
        st.Page("ade_home.py", title="Command Center", icon="🏠", default=True),
    ],
    "1. 오늘의 투자": [
        st.Page("pages/14_Recommendation_Workbench.py", title="투자 워크벤치", icon="📊"),
    ],
    "2. 운영 관리": [
        st.Page("pages/7_Daily_Center.py", title="한국 추천 배치", icon="🇰🇷"),
        st.Page("pages/10_US_Daily_Center.py", title="미국 추천 배치", icon="🇺🇸"),
        st.Page("pages/15_Validation_Report.py", title="종합 검증 리포트", icon="📋"),
        st.Page("pages/5_JP_Radar_Live.py", title="AI 레이더", icon="🎯"),
        st.Page("pages/16_KR_Validation_History.py", title="한국 검증 이력", icon="🧾"),
        st.Page("pages/17_US_Validation_History.py", title="미국 검증 이력", icon="🧾"),
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


MOBILE_PAGES = {
    "빠른 메뉴": [
        st.Page("ade_home.py", title="홈", icon="🏠", default=True),
        st.Page("pages/14_Recommendation_Workbench.py", title="워크벤치", icon="📊"),
        st.Page("pages/9_Trading_Desk.py", title="주문", icon="💳"),
        st.Page("pages/1_ADE_Cockpit.py", title="포트폴리오", icon="💼"),
    ],
    "전체 메뉴": [
        st.Page("pages/7_Daily_Center.py", title="한국 추천 배치", icon="🇰🇷"),
        st.Page("pages/10_US_Daily_Center.py", title="미국 추천 배치", icon="🇺🇸"),
        st.Page("pages/15_Validation_Report.py", title="종합 검증 리포트", icon="📋"),
        st.Page("pages/5_JP_Radar_Live.py", title="AI 레이더", icon="🎯"),
        st.Page("pages/16_KR_Validation_History.py", title="한국 검증 이력", icon="🧾"),
        st.Page("pages/17_US_Validation_History.py", title="미국 검증 이력", icon="🧾"),
        st.Page("pages/12_US_Trading_Desk.py", title="미국 주문", icon="🇺🇸"),
        st.Page("pages/3_Live_Monitor.py", title="실시간 모니터링", icon="📡"),
        st.Page("pages/6_Feedback.py", title="성과 분석", icon="📈"),
        st.Page("pages/4_KIS_Account.py", title="KIS 계좌", icon="🔐"),
        st.Page("pages/8_Mobile_Access.py", title="모바일", icon="📱"),
    ],
}


def _is_mobile_view() -> bool:
    value = st.query_params.get("view")
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value or "").lower() == "mobile"


def main() -> None:
    mobile = _is_mobile_view()
    navigation = st.navigation(
        MOBILE_PAGES if mobile else PAGES,
        position="top" if mobile else "sidebar",
        expanded=not mobile,
    )
    if mobile:
        st.caption("모바일 빠른 메뉴 · 전체 기능은 상단의 ‘전체 메뉴’에서 열 수 있습니다.")
    navigation.run()


if __name__ == "__main__":
    main()
