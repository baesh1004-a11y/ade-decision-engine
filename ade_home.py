from __future__ import annotations


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE Home", page_icon="◈", layout="wide")
    st.markdown(
        """
        <style>
        :root{
          --ink:#14263a;--muted:#6f8295;--line:rgba(77,125,168,.18);
          --glass:rgba(255,255,255,.84);--blue:#2f80ed;--blue-soft:#eaf3ff;
        }
        .stApp{background:radial-gradient(circle at 14% 0%,rgba(125,190,255,.22),transparent 28%),linear-gradient(135deg,#f7fbff 0%,#eef5fb 52%,#f9fcff 100%);color:var(--ink)}
        .block-container{max-width:1480px;padding-top:1.1rem;padding-bottom:3rem}
        [data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(248,252,255,.97),rgba(232,242,251,.98));border-right:1px solid var(--line)}
        [data-testid="stSidebar"] [data-testid="stSidebarNav"]{padding-top:.5rem}
        [data-testid="stSidebar"] a{border-radius:12px;margin:3px 8px;padding:9px 12px;color:#30475d!important;font-weight:650}
        [data-testid="stSidebar"] a:hover{background:rgba(47,128,237,.08)}
        [data-testid="stSidebar"] a[aria-current="page"]{background:linear-gradient(135deg,#dcecff,#eef6ff);color:#1768bd!important;box-shadow:inset 0 0 0 1px rgba(47,128,237,.16)}
        .hero{padding:34px 38px;border-radius:30px;background:linear-gradient(135deg,rgba(255,255,255,.94),rgba(241,248,255,.84));border:1px solid var(--line);box-shadow:0 24px 70px rgba(42,88,130,.13);margin-bottom:24px;position:relative;overflow:hidden}
        .hero:after{content:"";position:absolute;right:-70px;top:-95px;width:290px;height:290px;border-radius:50%;background:radial-gradient(circle,rgba(67,149,236,.22),rgba(67,149,236,0) 68%)}
        .hero h1{margin:5px 0 8px;font-size:42px;letter-spacing:-.045em;line-height:1.08}
        .hero p{margin:0;color:var(--muted);font-size:16px}.eyebrow{font-size:12px;letter-spacing:.17em;font-weight:850;color:#2f78ba}
        .market{padding:17px 21px;border-radius:18px;background:rgba(255,255,255,.72);border:1px solid var(--line);margin:22px 0 12px;display:flex;align-items:center;justify-content:space-between;gap:18px}
        .market h2{margin:0;font-size:22px;letter-spacing:-.03em}.market p{margin:0;color:var(--muted);font-size:14px;text-align:right}
        .card{padding:22px;border-radius:22px;background:var(--glass);border:1px solid var(--line);min-height:154px;box-shadow:0 12px 34px rgba(56,100,139,.09);transition:.18s ease}
        .card:hover{transform:translateY(-2px);box-shadow:0 18px 42px rgba(56,100,139,.13)}
        .card h3{margin:0 0 8px;font-size:19px;letter-spacing:-.025em}.card p{color:var(--muted);min-height:44px;line-height:1.55}
        div[data-testid="stPageLink"] a{border-radius:13px!important;border:1px solid rgba(47,128,237,.16)!important;background:linear-gradient(135deg,#f4f9ff,#e8f3ff)!important;color:#226bad!important;font-weight:800!important}
        div[data-testid="stCode"]{border-radius:18px;overflow:hidden;border:1px solid var(--line)}
        hr{border-color:var(--line)!important}
        @media(max-width:768px){.block-container{padding:.75rem}.hero{padding:24px}.hero h1{font-size:32px}.market{display:block}.market p{text-align:left;margin-top:6px}}
        </style>
        <div class="hero">
          <div class="eyebrow">ADE · DECISION OPERATIONS</div>
          <h1>AI Decision Engine</h1>
          <p>한국장과 미국장을 분리 운영하면서 추천, 판단, 주문, 피드백을 한 흐름으로 연결합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="market"><h2>🇰🇷 한국장 ADE</h2><p>FDR · datahub/market.db · KIS 국내주식</p></div>', unsafe_allow_html=True)
    kr_rows = [
        ("pages/7_Daily_Center.py", "KR Daily Center", "한국장 추천 생성과 실행 이력을 관리합니다."),
        ("pages/2_Meta_Score.py", "KR Meta Score", "Replay·Prediction·JP Radar를 통합해 최종 판단을 봅니다."),
        ("pages/9_Trading_Desk.py", "KR Trading Desk", "승인 절차를 거쳐 KIS 국내주식 주문을 전송합니다."),
    ]
    cols = st.columns(3)
    for col, (path, title, desc) in zip(cols, kr_rows):
        with col:
            st.markdown(f'<div class="card"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True)
            st.page_link(path, label=f"{title} 열기")

    st.markdown('<div class="market"><h2>🇺🇸 미국장 ADE</h2><p>yfinance · datahub/us_market.db · KIS 미국주식</p></div>', unsafe_allow_html=True)
    us_rows = [
        ("pages/10_US_Daily_Center.py", "US Daily Center", "미국장 전용 추천 생성과 실행 이력을 관리합니다."),
        ("pages/11_US_Meta_Score.py", "US Meta Score", "미국장 추천 결과를 별도 기준으로 통합 평가합니다."),
        ("pages/12_US_Trading_Desk.py", "US Trading Desk", "미국주식 모의·실전 주문을 승인형으로 관리합니다."),
        ("pages/5_JP_Radar_Live.py", "US JP Radar", "NASDAQ 30 또는 미국 개별 종목의 상태를 분석합니다."),
    ]
    for start in range(0, len(us_rows), 3):
        cols = st.columns(3)
        for col, (path, title, desc) in zip(cols, us_rows[start:start + 3]):
            with col:
                st.markdown(f'<div class="card"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True)
                st.page_link(path, label=f"{title} 열기")

    st.markdown('<div class="market"><h2>운영 도구</h2><p>검증 · 모니터링 · 계좌 · 피드백 · 모바일</p></div>', unsafe_allow_html=True)
    common_rows = [
        ("pages/1_ADE_Cockpit.py", "ADE Cockpit", "추천과 보유종목을 한 화면에서 검토합니다."),
        ("pages/3_Live_Monitor.py", "Live Monitor", "장중 가격과 상태 변화를 실시간으로 확인합니다."),
        ("pages/4_KIS_Account.py", "KIS Account", "국내 계좌 잔고와 보유종목을 동기화합니다."),
        ("pages/6_Feedback.py", "Feedback", "추천 이후 실제 성과를 기록하고 비교합니다."),
        ("pages/8_Mobile_Access.py", "Mobile Access", "같은 네트워크에서 휴대폰으로 접속합니다."),
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
        "# 한국장 Replay DB\n"
        "python run_build_replay_db.py\n\n"
        "# 미국장 가격 DB\n"
        "python run_build_us_market_db.py\n\n"
        "# 미국장 Replay 이벤트·흐름·벡터 DB\n"
        "python run_build_us_replay_db.py\n\n"
        "# 대시보드\n"
        "python run_ade.py",
        language="bash",
    )
    st.caption("미국 추천은 가격 데이터와 Replay 이벤트·벡터 구축이 모두 완료되어야 생성됩니다.")


if __name__ == "__main__":
    main()
