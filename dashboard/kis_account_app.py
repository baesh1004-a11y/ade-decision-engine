from __future__ import annotations

import argparse

import pandas as pd

from broker.kis_account_sync import KISAccountSync
from dashboard.design_system import StatusBadge, apply_design_system, page_header, section


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE KIS 계좌", page_icon="₩", layout="wide")
    apply_design_system()

    sync = KISAccountSync(db_path)
    try:
        account = sync.latest_account()
        page_header(
            "KIS 계좌",
            "KIS 모의계좌의 현금, 보유수량, 평균단가, 평가금액과 손익을 ADE 데이터베이스에 저장합니다.",
            eyebrow="ADE · KIS 계좌 동기화",
            badges=(
                StatusBadge("모의투자", "success"),
                StatusBadge("동기화 전" if account is None else "동기화 완료", "warning" if account is None else "success"),
            ),
        )

        c1, c2 = st.columns([1, 3])
        if c1.button("계좌 다시 불러오기", type="primary", use_container_width=True):
            try:
                snapshot, rows = sync.sync()
                st.success(f"{snapshot.captured_at} 기준 · 보유종목 {len(rows)}개를 동기화했습니다.")
                st.rerun()
            except Exception as exc:
                st.error(f"KIS 계좌 동기화 실패: {exc}")
        c2.caption("환경설정의 KIS 앱 키, 앱 시크릿, 계좌번호, 상품코드와 KIS_ENV=paper 값을 사용합니다.")

        account = sync.latest_account()
        positions = pd.DataFrame(sync.latest_positions())
        history = pd.DataFrame(sync.account_history())

        if account is None:
            st.info("저장된 KIS 계좌 스냅샷이 없습니다. 계좌 다시 불러오기를 실행하세요.")
            return

        total_asset = float(account["cash"]) + float(account["evaluation_amount"])
        invested = float(account["evaluation_amount"]) - float(account["pnl"])
        pnl_rate = float(account["pnl"]) / invested * 100.0 if invested > 0 else 0.0

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("주문가능 현금", f"{float(account['cash']):,.0f}원")
        k2.metric("평가금액", f"{float(account['evaluation_amount']):,.0f}원")
        k3.metric("총자산", f"{total_asset:,.0f}원")
        k4.metric("평가손익", f"{float(account['pnl']):+,.0f}원", f"{pnl_rate:+.2f}%")
        k5.metric("보유종목", f"{int(account['position_count'])}개")

        section("KIS 보유종목", "최근 동기화한 보유수량과 평가 현황입니다.")
        if positions.empty:
            st.info("현재 보유종목이 없습니다.")
        else:
            shown = positions.rename(
                columns={
                    "ticker": "종목코드",
                    "name": "종목명",
                    "quantity": "수량",
                    "average_price": "평균단가",
                    "current_price": "현재가",
                    "evaluation_amount": "평가금액",
                    "pnl": "평가손익",
                    "pnl_rate": "수익률",
                    "captured_at": "확인 시각",
                }
            )
            st.dataframe(
                shown,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "수량": st.column_config.NumberColumn(format="%d주"),
                    "평균단가": st.column_config.NumberColumn(format="%,.0f원"),
                    "현재가": st.column_config.NumberColumn(format="%,.0f원"),
                    "평가금액": st.column_config.NumberColumn(format="%,.0f원"),
                    "평가손익": st.column_config.NumberColumn(format="%+,.0f원"),
                    "수익률": st.column_config.NumberColumn(format="%+.2f%%"),
                },
            )

        section("계좌 평가 추이", "현금·평가금액·평가손익의 시간별 변화를 확인합니다.")
        if history.empty:
            st.info("계좌 평가 이력이 없습니다.")
        else:
            history["captured_at"] = pd.to_datetime(history["captured_at"])
            chart = history.set_index("captured_at")[["cash", "evaluation_amount", "pnl"]].rename(
                columns={"cash": "현금", "evaluation_amount": "평가금액", "pnl": "평가손익"}
            )
            st.line_chart(chart, height=380)
            shown_history = history.tail(50).rename(
                columns={
                    "captured_at": "확인 시각",
                    "cash": "현금",
                    "evaluation_amount": "평가금액",
                    "pnl": "평가손익",
                    "position_count": "보유종목 수",
                }
            )
            st.dataframe(shown_history, use_container_width=True, hide_index=True)

        st.caption(f"마지막 동기화: {account['captured_at']}")
    finally:
        sync.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE KIS 계좌 대시보드")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
