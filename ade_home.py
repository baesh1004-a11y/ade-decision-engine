from __future__ import annotations


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE Home", page_icon="◈", layout="wide")
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1500px;padding-top:1.25rem}
        .hero{padding:28px 32px;border-radius:28px;background:rgba(255,255,255,.84);border:1px solid rgba(72,145,210,.22);box-shadow:0 18px 50px rgba(63,105,145,.12);margin-bottom:18px}
        .hero h1{margin:2px 0;font-size:40px;letter-spacing:-.045em}.hero p{margin:7px 0;color:#647b92}.eyebrow{font-size:12px;letter-spacing:.16em;font-weight:800;color:#3479b9}
        .market{padding:18px 22px;border-radius:22px;background:rgba(255,255,255,.88);border:1px solid rgba(72,145,210,.20);margin:14px 0 10px}.market h2{margin:0}.market p{margin:5px 0;color:#687d92}
        .card{padding:20px;border-radius:22px;background:rgba(255,255,255,.82);border:1px solid rgba(72,145,210,.18);min-height:145px;box-shadow:0 10px 32px rgba(63,105,145,.09)}
        .card h3{margin:0 0 8px}.card p{color:#687d92;min-height:48px}
        @media(max-width:768px){.block-container{padding:.75rem}.hero{padding:20px}.hero h1{font-size:30px}}
        </style>
        <div class="hero">
          <div class="eyebrow">ADE · SEPARATED MARKET WORKSPACES</div>
          <h1>AI Decision Engine Home</h1>
          <p>한국장과 미국장을 서로 다른 DB·추천 이력·주문 화면으로 분리합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="market"><h2>🇰🇷 한국장 ADE</h2><p>DB: datahub/market.db · FDR 기반 · KIS 국내주식 주문</p></div>', unsafe_allow_html=True)
    kr_rows = [
        ("pages/7_Daily_Center.py", "KR Daily Center", "한국장 추천 생성과 이력"),
        ("pages/2_Meta_Score.py", "KR Meta Score", "한국장 추천 통합점수"),
        ("pages/9_Trading_Desk.py", "KR Trading Desk", "KIS 국내주식 승인 주문"),
    ]
    cols = st.columns(3)
    for col, (path, title, desc) in zip(cols, kr_rows):
        with col:
            st.markdown(f'<div class="card"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True)
            st.page_link(path, label=f"{title} 열기")

    st.markdown('<div class="market"><h2>🇺🇸 미국장 ADE</h2><p>DB: datahub/us_market.db · yfinance 기반 · KIS 미국주식 모의주문</p></div>', unsafe_allow_html=True)
    us_rows = [
        ("pages/10_US_Daily_Center.py", "US Daily Center", "미국장 전용 추천 생성과 이력"),
        ("pages/11_US_Meta_Score.py", "US Meta Score", "미국장 전용 통합점수"),
        ("pages/12_US_Trading_Desk.py", "US Trading Desk", "KIS 미국주식 모의·승인 주문"),
        ("pages/5_JP_Radar_Live.py", "US JP Radar", "NASDAQ 30 또는 미국 개별 종목 분석"),
    ]
    for start in range(0, len(us_rows), 3):
        cols = st.columns(3)
        for col, (path, title, desc) in zip(cols, us_rows[start:start + 3]):
            with col:
                st.markdown(f'<div class="card"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True)
                st.page_link(path, label=f"{title} 열기")

    st.markdown('<div class="market"><h2>공통 운영 도구</h2><p>계좌·모니터·Feedback·모바일 접속</p></div>', unsafe_allow_html=True)
    common_rows = [
        ("pages/1_ADE_Cockpit.py", "ADE Cockpit", "추천 검증과 보유종목"),
        ("pages/3_Live_Monitor.py", "Live Monitor", "장중 현재가 모니터"),
        ("pages/4_KIS_Account.py", "KIS Account", "국내 계좌 잔고 동기화"),
        ("pages/6_Feedback.py", "Feedback", "추천 이후 성과 통계"),
        ("pages/8_Mobile_Access.py", "Mobile Access", "휴대폰 접속 안내"),
    ]
    for start in range(0, len(common_rows), 3):
        cols = st.columns(3)
        for col, (path, title, desc) in zip(cols, common_rows[start:start + 3]):
            with col:
                st.markdown(f'<div class="card"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True)
                st.page_link(path, label=f"{title} 열기")

    st.divider()
    st.markdown("### 시장별 DB 구축")
    st.code(
        "# 한국장 기존 DB\n"
        "python run_build_replay_db.py\n\n"
        "# 미국장 가격 DB\n"
        "python run_build_us_market_db.py\n\n"
        "# 대시보드\n"
        "python run_ade.py",
        language="bash",
    )
    st.caption("미국주식 모의투자는 지정가 주문만 지원하며, 주문 승인 문구를 직접 입력해야 KIS로 전송됩니다.")


if __name__ == "__main__":
    main()
