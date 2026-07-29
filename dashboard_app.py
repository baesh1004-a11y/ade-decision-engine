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


def main() -> None:
    apply_design_system()
    navigation = st.navigation(
        PAGES,
        position="sidebar",
        expanded=False,
    )
    navigation.run()

    st.markdown(
        """
        <style>
        .ade-mobile-top-nav{display:none}
        @media(max-width:640px){
          [data-testid="stSidebar"]{display:none!important}
          [data-testid="stSidebarCollapsedControl"]{display:none!important}
          .ade-mobile-top-nav{
            position:fixed;
            left:0;
            right:0;
            top:0;
            bottom:auto;
            z-index:9999;
            display:grid;
            grid-template-columns:repeat(5,minmax(0,1fr));
            gap:0;
            padding:calc(4px + env(safe-area-inset-top)) 6px 4px;
            border:0;
            border-bottom:1px solid #d1d5db;
            border-radius:0;
            background:#ffffff;
            box-shadow:none;
            backdrop-filter:none;
          }
          .ade-mobile-top-nav a{
            min-width:0;
            min-height:48px;
            padding:4px 2px;
            border-radius:0;
            color:#6b7280;
            text-decoration:none;
            display:flex;
            flex-direction:column;
            align-items:center;
            justify-content:center;
            gap:2px;
            font-size:10px;
            font-weight:750;
            line-height:1;
            white-space:nowrap;
          }
          .ade-mobile-top-nav a span:first-child{font-size:17px;line-height:1}
          .ade-mobile-top-nav a:hover,.ade-mobile-top-nav a:focus{
            background:#f8fafc;
            color:#2563eb;
          }
          [data-testid="stAppViewContainer"] .main .block-container{
            padding-top:calc(60px + env(safe-area-inset-top))!important;
            padding-bottom:18px!important;
          }
        }
        </style>
        <nav class="ade-mobile-top-nav" aria-label="모바일 빠른 메뉴">
          <a href="/" target="_self"><span>🏠</span><span>홈</span></a>
          <a href="/Recommendation_Workbench" target="_self"><span>📊</span><span>추천</span></a>
          <a href="/Trading_Desk" target="_self"><span>💳</span><span>주문</span></a>
          <a href="/Scheduled_Orders" target="_self"><span>🗓️</span><span>예약</span></a>
          <a href="/ADE_Cockpit" target="_self"><span>💼</span><span>성과</span></a>
        </nav>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
