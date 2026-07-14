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
        .card{padding:20px;border-radius:22px;background:rgba(255,255,255,.82);border:1px solid rgba(72,145,210,.18);min-height:145px;box-shadow:0 10px 32px rgba(63,105,145,.09)}
        .card h3{margin:0 0 8px}.card p{color:#687d92;min-height:48px}
        @media(max-width:768px){.block-container{padding:.75rem}.hero{padding:20px}.hero h1{font-size:30px}}
        </style>
        <div class="hero">
          <div class="eyebrow">ADE · UNIFIED OPERATIONS</div>
          <h1>AI Decision Engine Home</h1>
          <p>추천, Meta Score, KIS 주문, 실시간 모니터, JP Radar, Feedback을 한 실행에서 이동합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    rows = [
        ("pages/7_Daily_Center.py", "Daily Center", "평일 16:10 자동 추천과 장중 수동 추천을 통합 운영"),
        ("pages/9_Trading_Desk.py", "KIS Trading Desk", "매수 요청, 사용자 승인, 주문·체결 확인, 손절·익절 감시"),
        ("pages/1_ADE_Cockpit.py", "ADE Cockpit", "추천 검증, 보유종목, 주문내역, 매도판단"),
        ("pages/2_Meta_Score.py", "Meta Score", "Replay·Prediction·JP Radar·Risk 통합점수"),
        ("pages/3_Live_Monitor.py", "Live Monitor", "추천종목과 보유종목 장중 KIS 현재가 모니터"),
        ("pages/4_KIS_Account.py", "KIS Account", "모의·실전계좌 현금·잔고·평가손익 동기화"),
        ("pages/5_JP_Radar_Live.py", "JP Radar Live", "시장·업종 에너지와 장중 지수·MACD"),
        ("pages/6_Feedback.py", "Feedback", "추천 이후 일별 성과와 종목별 통계"),
        ("pages/8_Mobile_Access.py", "Mobile Access", "같은 Wi-Fi에서 휴대폰으로 ADE 접속"),
    ]

    for start in range(0, len(rows), 3):
        cols = st.columns(3)
        for col, (path, title, desc) in zip(cols, rows[start:start + 3]):
            with col:
                st.markdown(f'<div class="card"><h3>{title}</h3><p>{desc}</p></div>', unsafe_allow_html=True)
                st.page_link(path, label=f"{title} 열기")

    st.divider()
    st.markdown("### 운영 명령")
    st.code(
        "python run_build_replay_db.py\n"
        "python run_recommend_v3.py\n"
        "python run_paper_trading.py --execute\n"
        "python run_feedback_update.py",
        language="bash",
    )
    st.caption("실제 주문은 Trading Desk에서 주문 요청 생성 후 승인 문구를 직접 입력해야 전송됩니다.")


if __name__ == "__main__":
    main()
