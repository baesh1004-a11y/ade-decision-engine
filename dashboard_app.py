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

MOBILE_PAGES = [
    st.Page("ade_home.py", title="홈", icon="🏠", default=True),
    st.Page("pages/14_Recommendation_Workbench.py", title="추천", icon="📊"),
    st.Page("pages/9_Trading_Desk.py", title="주문", icon="💳"),
    st.Page("pages/15_Scheduled_Orders.py", title="예약", icon="🗓️"),
    st.Page("pages/1_ADE_Cockpit.py", title="성과", icon="💼"),
]


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
        .ade-mobile-bottom-nav{display:none}
        @media(max-width:640px){
          [data-testid="stSidebar"]{display:none!important}
          [data-testid="stSidebarCollapsedControl"]{display:none!important}
          .ade-mobile-bottom-nav{
            position:fixed;
            left:8px;
            right:8px;
            bottom:8px;
            z-index:9999;
            display:grid;
            grid-template-columns:repeat(5,minmax(0,1fr));
            gap:2px;
            padding:5px;
            border:1px solid rgba(50,84,119,.14);
            border-radius:16px;
            background:rgba(255,255,255,.94);
            box-shadow:0 10px 28px rgba(29,62,96,.16);
            backdrop-filter:blur(14px);
          }
          .ade-mobile-bottom-nav a{
            min-width:0;
            min-height:42px;
            padding:4px 2px;
            border-radius:11px;
            color:#6f8194;
            text-decoration:none;
            display:flex;
            flex-direction:column;
            align-items:center;
            justify-content:center;
            gap:1px;
            font-size:10px;
            font-weight:800;
            line-height:1;
            white-space:nowrap;
          }
          .ade-mobile-bottom-nav a span:first-child{font-size:16px;line-height:1}
          .ade-mobile-bottom-nav a:hover,.ade-mobile-bottom-nav a:focus{
            background:#edf5ff;
            color:#19559a;
          }
          [data-testid="stAppViewContainer"] .main .block-container{padding-bottom:76px!important}
        }
        </style>
        <nav class="ade-mobile-bottom-nav" aria-label="모바일 빠른 메뉴">
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
