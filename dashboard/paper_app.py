from __future__ import annotations

import argparse

import pandas as pd

from dashboard.data import PaperDashboardData


def _money(value: float) -> str:
    return f"{value:,.0f}원"


def _pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _run_streamlit(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE Paper Trading", page_icon="📈", layout="wide")
    st.markdown(
        """
        <style>
        .stApp { background: linear-gradient(135deg, #eef6ff 0%, #f8fbff 100%); }
        .block-container { padding-top: 2rem; max-width: 1500px; }
        .ade-hero { padding: 22px 26px; border: 1px solid #dbe5f2; border-radius: 28px; background: rgba(255,255,255,.78); box-shadow: 0 18px 50px rgba(45,91,154,.08); backdrop-filter: blur(12px); margin-bottom: 18px; }
        .ade-hero h1 { margin: 0; letter-spacing: -.04em; font-size: 38px; color: #162033; }
        .ade-hero p { margin: 6px 0 0; color: #6b778c; }
        .metric-card { padding: 18px; border: 1px solid #dbe5f2; border-radius: 22px; background: rgba(255,255,255,.82); box-shadow: 0 14px 40px rgba(45,91,154,.07); }
        .metric-card label { color: #6b778c; font-size: 13px; }
        .metric-card strong { display:block; margin-top: 8px; font-size: 25px; color: #162033; }
        .pos { color:#10a37f !important; }
        .neg { color:#d64545 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="ade-hero">
          <h1>ADE Paper Trading Dashboard</h1>
          <p>추천종목 전부 모의매수 · 종목당 100만원 · Replay 근거 추적</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    data = PaperDashboardData(db_path)
    try:
        metrics = data.metrics()
        positions = data.load_positions()
        orders = data.load_orders()
        curve = data.equity_curve()
    finally:
        data.close()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    cards = [
        (c1, "투자원금", _money(metrics.invested_amount), ""),
        (c2, "평가금액", _money(metrics.evaluation_amount), ""),
        (c3, "평가손익", _money(metrics.pnl), "pos" if metrics.pnl >= 0 else "neg"),
        (c4, "수익률", _pct(metrics.pnl_rate), "pos" if metrics.pnl_rate >= 0 else "neg"),
        (c5, "보유종목", f"{len(positions)}개", ""),
        (c6, "승/패", f"{metrics.winners}/{metrics.losers}", ""),
    ]
    for col, label, value, cls in cards:
        col.markdown(f'<div class="metric-card"><label>{label}</label><strong class="{cls}">{value}</strong></div>', unsafe_allow_html=True)

    st.divider()

    left, right = st.columns([1.6, 1])
    with left:
        st.subheader("보유종목")
        if positions.empty:
            st.info("아직 저장된 모의매수 포지션이 없습니다. `python run_paper_trading.py --execute` 실행 후 확인하세요.")
        else:
            view = positions.copy()
            for col in ["invested_amount", "evaluation_amount", "pnl", "current_price", "avg_reference_price"]:
                view[col] = view[col].map(lambda x: round(float(x), 2))
            view = view[[
                "market", "ticker", "name", "quantity", "avg_reference_price", "current_price",
                "invested_amount", "evaluation_amount", "pnl", "pnl_rate",
                "final_similarity", "weekly_similarity", "sto_similarity", "top1_event_id",
            ]]
            st.dataframe(view, use_container_width=True, hide_index=True)

    with right:
        st.subheader("투자원금 누적")
        if curve.empty:
            st.info("주문 기록이 없습니다.")
        else:
            chart = curve.copy()
            chart["date"] = pd.to_datetime(chart["date"])
            st.line_chart(chart.set_index("date")["invested"], height=300)

    st.divider()

    st.subheader("최근 주문 기록")
    if orders.empty:
        st.info("주문 기록이 없습니다.")
    else:
        recent = orders.head(100).copy()
        show_cols = [
            "created_at", "market", "ticker", "name", "side", "quantity", "reference_price",
            "estimated_amount", "accepted", "order_id", "message", "final_similarity", "top1_event_id",
        ]
        st.dataframe(recent[[c for c in show_cols if c in recent.columns]], use_container_width=True, hide_index=True)

    st.caption("매도 로직은 아직 적용하지 않았습니다. 현재 화면은 모의매수 주문과 보유 평가 확인용입니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE Paper Trading Dashboard")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    _run_streamlit(args.db)


if __name__ == "__main__":
    main()
