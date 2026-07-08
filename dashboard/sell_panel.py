from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from broker.kis import kis_broker_from_env
from paper_trading.order_manager import PaperOrderManager
from paper_trading.portfolio import PaperPortfolioRepository
from paper_trading.sell_advisor import PaperSellAdvisor


def render_sell_panel(st: object, db_path: str, positions: pd.DataFrame) -> None:
    st.markdown("<div class='panel-title'>매도 판단 대시보드</div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="chart-empty">
        ADE는 매도 후보와 이유만 제시합니다. 실제 주문은 사용자가 종목과 수량을 확인하고 승인할 때만 전송됩니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if positions.empty:
        st.info("보유 중인 모의투자 종목이 없습니다.")
        return

    advisor = PaperSellAdvisor(db_path)
    try:
        advice = advisor.evaluate_positions(positions)
    finally:
        advisor.close()

    table = pd.DataFrame([asdict(item) for item in advice])
    st.dataframe(
        table[[
            "decision", "score", "market", "ticker", "name", "quantity",
            "current_price", "pnl_rate", "replay_progress_pct", "target_return", "replay_mdd",
        ]],
        use_container_width=True,
        hide_index=True,
    )

    sell_count = sum(1 for item in advice if item.decision == "SELL")
    watch_count = sum(1 for item in advice if item.decision == "WATCH")
    hold_count = sum(1 for item in advice if item.decision == "HOLD")
    a, b, c = st.columns(3)
    a.metric("매도 추천", sell_count)
    b.metric("주의", watch_count)
    c.metric("보유", hold_count)

    selected = st.selectbox(
        "판단할 보유종목",
        list(range(len(advice))),
        format_func=lambda i: f"{advice[i].decision} {advice[i].score}점 · {advice[i].name or advice[i].ticker} · {advice[i].ticker}",
    )
    item = advice[selected]

    cls = "neg" if item.decision == "SELL" else "pos" if item.decision == "HOLD" else ""
    st.markdown(
        f"""
        <div class="replay-card">
          <div>
            <div class="eyebrow">SELL DECISION MATERIAL</div>
            <h2>{item.name or item.ticker} <small>{item.market.upper()}:{item.ticker}</small></h2>
          </div>
          <div class="replay-score {cls}">{item.decision} · {item.score}점</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("현재 수익률", f"{item.pnl_rate:+.2f}%")
    m2.metric("현재가", f"{item.current_price:,.0f}원")
    m3.metric("보유수량", f"{item.quantity:,}주")
    m4.metric("Replay 진행률", "-" if item.replay_progress_pct is None else f"{item.replay_progress_pct:.0f}%")
    m5.metric("Replay 목표수익", "-" if item.target_return is None else f"{item.target_return:.1f}%")

    st.markdown("<div class='panel-title'>매도 추천 이유</div>", unsafe_allow_html=True)
    for reason in item.reasons:
        st.markdown(f"- {reason}")

    if item.replay_week is not None and item.replay_total_weeks:
        st.progress(min(1.0, item.replay_week / max(item.replay_total_weeks, 1)))
        st.caption(f"Replay Week {item.replay_week} / {item.replay_total_weeks} · {item.replay_event_id or '-'}")

    st.markdown("<div class='panel-title'>사용자 승인 후 모의매도</div>", unsafe_allow_html=True)
    sell_quantity = st.number_input(
        "매도 수량",
        min_value=1,
        max_value=max(1, item.quantity),
        value=max(1, item.quantity),
        step=1,
        key=f"sell_qty_{item.market}_{item.ticker}",
    )
    confirm = st.checkbox(
        f"{item.name or item.ticker} {int(sell_quantity)}주를 현재 기준가 약 {item.current_price:,.0f}원에 모의매도하는 것에 동의합니다.",
        key=f"sell_confirm_{item.market}_{item.ticker}",
    )

    preview_col, execute_col = st.columns(2)
    if preview_col.button("매도 주문 미리보기", key=f"sell_preview_{item.market}_{item.ticker}"):
        position = positions[(positions["market"].astype(str).str.lower() == item.market) & (positions["ticker"].astype(str) == item.ticker)].iloc[0]
        manager = PaperOrderManager(db_path)
        try:
            plan = manager.build_sell_plan(position, int(sell_quantity))
        finally:
            manager.close()
        if plan is None:
            st.error("매도 주문계획을 만들 수 없습니다.")
        else:
            st.success(
                f"SELL {plan.market.upper()}:{plan.ticker} · {plan.quantity}주 · 기준가 {plan.reference_price:,.0f}원 · 예상금액 {plan.estimated_amount:,.0f}원"
            )

    if execute_col.button("KIS 모의매도 실행", type="primary", disabled=not confirm, key=f"sell_execute_{item.market}_{item.ticker}"):
        position = positions[(positions["market"].astype(str).str.lower() == item.market) & (positions["ticker"].astype(str) == item.ticker)].iloc[0]
        manager = PaperOrderManager(db_path)
        portfolio = PaperPortfolioRepository(db_path)
        try:
            plan = manager.build_sell_plan(position, int(sell_quantity))
            if plan is None:
                st.error("매도 주문계획을 만들 수 없습니다.")
                return
            broker = kis_broker_from_env()
            executions = manager.execute(broker, [plan], dry_run=False)
            portfolio.save_executions(executions)
        finally:
            manager.close()
            portfolio.close()

        execution = executions[0]
        if execution.accepted:
            st.success(f"모의매도 주문이 접수되었습니다. 주문번호: {execution.order_id or '-'}")
            st.rerun()
        else:
            st.error(f"모의매도 주문이 거절되었습니다: {execution.message}")
