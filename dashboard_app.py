from __future__ import annotations

import streamlit as st


PAGES = {
    "DISCOVERY": [
        st.Page("ade_home.py", title="Command Center", icon="🏠", default=True),
        st.Page("pages/13_Surge_Pattern_Lab.py", title="AI Pattern Lab", icon="📈"),
        st.Page("pages/5_JP_Radar_Live.py", title="AI Radar", icon="🎯"),
    ],
    "KOREA": [
        st.Page("pages/7_Daily_Center.py", title="Korea Picks", icon="🇰🇷"),
        st.Page("pages/2_Meta_Score.py", title="Korea Decision", icon="🧠"),
        st.Page("pages/9_Trading_Desk.py", title="Korea Trading", icon="💳"),
    ],
    "USA": [
        st.Page("pages/10_US_Daily_Center.py", title="US Picks", icon="🇺🇸"),
        st.Page("pages/11_US_Meta_Score.py", title="US Decision", icon="📊"),
        st.Page("pages/12_US_Trading_Desk.py", title="US Trading", icon="💵"),
    ],
    "PORTFOLIO": [
        st.Page("pages/1_ADE_Cockpit.py", title="Portfolio Cockpit", icon="🖥️"),
        st.Page("pages/3_Live_Monitor.py", title="Live Monitor", icon="📡"),
        st.Page("pages/6_Feedback.py", title="Performance", icon="📋"),
    ],
    "SYSTEM": [
        st.Page("pages/4_KIS_Account.py", title="KIS Account", icon="🏦"),
        st.Page("pages/8_Mobile_Access.py", title="Mobile Access", icon="📱"),
    ],
}


def main() -> None:
    navigation = st.navigation(PAGES, position="sidebar", expanded=True)
    navigation.run()


if __name__ == "__main__":
    main()
