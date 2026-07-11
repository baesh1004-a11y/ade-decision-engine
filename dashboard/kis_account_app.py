from __future__ import annotations

import argparse

import pandas as pd

from broker.kis_account_sync import KISAccountSync


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE KIS Account", page_icon="₩", layout="wide")
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1550px;padding-top:1.2rem}
        .hero{padding:24px 28px;border-radius:26px;background:rgba(255,255,255,.84);border:1px solid rgba(72,145,210,.22);box-shadow:0 18px 48px rgba(64,106,147,.12);margin-bottom:16px}
        .hero h1{margin:3px 0}.hero p{margin:5px 0;color:#687d92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        </style>
        <div class="hero"><div class="eyebrow">KIS PAPER ACCOUNT SYNC</div><h1>모의계좌 잔고·평가 현황</h1><p>KIS 모의계좌의 현금, 보유수량, 평균단가, 평가금액과 손익을 ADE DB에 저장합니다.</p></div>
        """,
        unsafe_allow_html=True,
    )

    sync = KISAccountSync(db_path)
    try:
        c1, c2 = st.columns([1, 3])
        if c1.button("KIS 계좌 동기화", type="primary"):
            try:
                snapshot, rows = sync.sync()
                st.success(f"{snapshot.captured_at} 기준 · 보유종목 {len(rows)}개 동기화 완료")
            except Exception as exc:
                st.error(f"KIS 계좌 동기화 실패: {exc}")
        c2.caption(".env의 KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT, KIS_PRODUCT_CODE, KIS_ENV=paper 설정을 사용합니다.")

        account = sync.latest_account()
        positions = pd.DataFrame(sync.latest_positions())
        history = pd.DataFrame(sync.account_history())

        if account is None:
            st.info("저장된 KIS 계좌 스냅샷이 없습니다. 계좌 동기화 버튼을 누르세요.")
            return

        total_asset = float(account["cash"]) + float(account["evaluation_amount"])
        pnl_rate = 0.0
        invested = float(account["evaluation_amount"]) - float(account["pnl"])
        if invested > 0:
            pnl_rate = float(account["pnl"]) / invested * 100.0

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("주문가능 현금", f"{float(account['cash']):,.0f}원")
        k2.metric("평가금액", f"{float(account['evaluation_amount']):,.0f}원")
        k3.metric("총자산", f"{total_asset:,.0f}원")
        k4.metric("평가손익", f"{float(account['pnl']):+,.0f}원", f"{pnl_rate:+.2f}%")
        k5.metric("보유종목", f"{int(account['position_count'])}개")

        st.markdown("### KIS 보유종목")
        if positions.empty:
            st.caption("현재 보유종목이 없습니다.")
        else:
            st.dataframe(
                positions,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "quantity": st.column_config.NumberColumn("수량", format="%d주"),
                    "average_price": st.column_config.NumberColumn("평균단가", format="%,.0f원"),
                    "current_price": st.column_config.NumberColumn("현재가", format="%,.0f원"),
                    "evaluation_amount": st.column_config.NumberColumn("평가금액", format="%,.0f원"),
                    "pnl": st.column_config.NumberColumn("평가손익", format="%+,.0f원"),
                    "pnl_rate": st.column_config.NumberColumn("수익률", format="%+.2f%%"),
                },
            )

        st.markdown("### 계좌 평가 추이")
        if not history.empty:
            history["captured_at"] = pd.to_datetime(history["captured_at"])
            chart = history.set_index("captured_at")[["cash", "evaluation_amount", "pnl"]]
            st.line_chart(chart, height=380)
            st.dataframe(history.tail(50), use_container_width=True, hide_index=True)

        st.caption(f"최종 저장 시각: {account['captured_at']}")
    finally:
        sync.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE KIS account dashboard")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
