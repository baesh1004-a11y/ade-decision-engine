from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from dashboard.data import PaperDashboardData
from dashboard.paper_app import (
    _capital_timeline,
    _inject_style,
    _latest_orders_cards,
    _metric,
    _orders_table,
    _portfolio_radar,
    _position_heatmap,
    _positions_table,
    _replay_basis,
    _system_status,
    _top_movers,
)
from dashboard.sell_panel import render_sell_panel
from maintenance.job_manager import ADEJobManager
from recommendation.daily_service import DailyRecommendationService
from recommendation.event_recommender import RecentMoneyEventRecommender
from report.chart_viewer import RecommendationChartViewer


def _fmt(value: object, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.00"


def _run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE AI Trading Cockpit", page_icon="◈", layout="wide")
    _inject_style(st)

    data = PaperDashboardData(db_path)
    try:
        metrics = data.metrics()
        positions = data.load_positions()
        orders = data.load_orders()
        curve = data.equity_curve()
    finally:
        data.close()

    st.markdown(
        """
        <div class="top-hero">
          <div>
            <div class="eyebrow">ADE v5 · INTEGRATED DECISION COCKPIT</div>
            <h1>AI Decision Engine</h1>
            <p>추천 생성 · 추천 검증 · 보유 판단 · 사용자 승인 모의매도를 한 화면에서 확인합니다.</p>
          </div>
          <div class="hero-status"><span class="pulse"></span>PAPER MODE</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    _metric(k1, "투자원금", f"{metrics.invested_amount:,.0f}원", "Capital deployed")
    _metric(k2, "평가금액", f"{metrics.evaluation_amount:,.0f}원", "Current valuation")
    _metric(k3, "평가손익", f"{metrics.pnl:,.0f}원", "Unrealized P/L", metrics.pnl)
    _metric(k4, "수익률", f"{metrics.pnl_rate:+.2f}%", "Portfolio return", metrics.pnl_rate)
    _metric(k5, "보유종목", f"{len(positions)}개", "Open positions")
    _metric(k6, "승 / 패", f"{metrics.winners} / {metrics.losers}", "Positive / Negative")

    st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["◈ Cockpit", "▣ Positions", "⌁ Replay Basis", "◎ Orders", "📑 추천 검증 리포트", "🔻 매도 판단"]
    )

    with tab1:
        left, center, right = st.columns([1.05, 1.55, 1.0])
        with left:
            st.markdown("<div class='panel-title'>Portfolio Radar</div>", unsafe_allow_html=True)
            _portfolio_radar(st, positions)
            st.markdown("<div class='panel-title'>Top Movers</div>", unsafe_allow_html=True)
            _top_movers(st, positions)
        with center:
            st.markdown("<div class='panel-title'>Capital Timeline</div>", unsafe_allow_html=True)
            _capital_timeline(st, curve)
            st.markdown("<div class='panel-title'>Position Heatmap</div>", unsafe_allow_html=True)
            _position_heatmap(st, positions)
        with right:
            st.markdown("<div class='panel-title'>System Status</div>", unsafe_allow_html=True)
            _system_status(st, orders, positions)
            st.markdown("<div class='panel-title'>Latest Orders</div>", unsafe_allow_html=True)
            _latest_orders_cards(st, orders)

    with tab2:
        st.markdown("<div class='panel-title'>Open Positions</div>", unsafe_allow_html=True)
        _positions_table(st, positions)

    with tab3:
        st.markdown("<div class='panel-title'>Replay Basis Monitor</div>", unsafe_allow_html=True)
        _replay_basis(st, positions)

    with tab4:
        st.markdown("<div class='panel-title'>Order History</div>", unsafe_allow_html=True)
        _orders_table(st, orders)

    with tab5:
        _recommendation_report(st, db_path)

    with tab6:
        render_sell_panel(st, db_path, positions)

    st.caption("ADE Integrated Dashboard · 매도는 자동 실행하지 않으며 사용자가 직접 승인한 KIS 모의주문만 전송합니다.")


def _recommendation_report(st: object, db_path: str) -> None:
    st.markdown("<div class='panel-title'>ADE Recommendation Verification Report</div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="chart-empty">
        현재 시점 추천종목을 생성·저장한 뒤, 추천 사유와 Top5 Replay를 상세 검증합니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    top_n = c1.number_input("추천 수", min_value=1, max_value=30, value=10, step=1, key="report_top_n")
    weekly_pool = c2.number_input("Weekly Pool", min_value=20, max_value=300, value=100, step=10, key="report_pool")
    min_weekly = c3.number_input("주봉 기준", min_value=70.0, max_value=99.0, value=85.0, step=1.0, key="report_weekly")
    min_sto = c4.number_input("STO 기준", min_value=70.0, max_value=99.0, value=85.0, step=1.0, key="report_sto")

    manager = ADEJobManager()
    current_job = manager.current_status() or {}
    j1, j2, j3 = st.columns(3)
    j1.metric("ADE 작업 상태", str(current_job.get("state", "IDLE")))
    j2.metric("현재 작업", str(current_job.get("job_name", "없음")))
    j3.metric("최근 갱신", str(current_job.get("updated_at", "없음")))

    generate_col, verify_col = st.columns(2)
    generate_clicked = generate_col.button(
        "추천종목 생성 및 저장",
        type="primary",
        use_container_width=True,
        key="generate_recommendations",
    )
    verify_clicked = verify_col.button(
        "추천 검증 리포트 생성",
        use_container_width=True,
        key="verify_recommendations",
    )

    if generate_clicked:
        with st.status("현재 시점 추천종목을 생성하고 있습니다...", expanded=True) as status:
            service = DailyRecommendationService(db_path)
            try:
                st.write("다른 DB 작업 종료 대기")
                with manager.acquire(
                    "MANUAL_RECOMMENDATION",
                    wait=True,
                    timeout_seconds=6 * 60 * 60,
                ):
                    st.write("Replay Vector 및 주봉·STO 유사도 계산")
                    result = service.run(
                        "MANUAL",
                        top_n=int(top_n),
                        weekly_pool_n=int(weekly_pool),
                        min_weekly_similarity=float(min_weekly),
                        min_sto_similarity=float(min_sto),
                        replay_top_n=5,
                    )
                status.update(label="추천종목 생성 완료", state="complete", expanded=False)
                st.success(
                    f"추천 {result.recommendation_count}개 저장 완료 · "
                    f"소요시간 {result.elapsed_seconds:.1f}초 · {result.run_id}"
                )
                st.caption(f"HTML 보고서: {result.report_path}")
            except Exception as exc:
                status.update(label="추천종목 생성 실패", state="error", expanded=True)
                st.error(str(exc))
            finally:
                service.close()

    if verify_clicked:
        with st.status("추천 검증 리포트를 계산하고 있습니다...", expanded=False) as status:
            engine = RecentMoneyEventRecommender(db_path=db_path)
            try:
                recommendations = engine.recommend(
                    candidate_years=2,
                    lookback_months=6,
                    top_n=int(top_n),
                    weekly_pool_n=int(weekly_pool),
                    min_weekly_similarity=float(min_weekly),
                    min_sto_similarity=float(min_sto),
                    replay_top_n=5,
                )
            finally:
                engine.close()
            st.session_state["dashboard_recommendation_report"] = recommendations
            st.session_state.pop("dashboard_report_charts", None)
            status.update(label="추천 검증 리포트 생성 완료", state="complete")

    rows = st.session_state.get("dashboard_recommendation_report", [])
    if not rows:
        st.info("먼저 추천종목을 생성·저장하거나, 추천 검증 리포트 생성 버튼을 누르세요.")
        return

    summary = pd.DataFrame(
        [
            {
                "rank": idx,
                "market": item.market.upper(),
                "ticker": item.ticker,
                "name": item.name,
                "decision": item.decision,
                "final": round(float(item.final_similarity), 2),
                "weekly": round(float(item.weekly_similarity), 2),
                "sto": round(float(item.sto_similarity), 2),
                "top1_replay": item.matched_event_id,
                "top1_max_return": item.matched_max_return,
                "top1_mdd": item.matched_max_drawdown,
                "recent_event": item.recent_event_date,
                "money_ratio": item.recent_money_ratio,
            }
            for idx, item in enumerate(rows, start=1)
        ]
    )

    recommend_count = int((summary["decision"] == "RECOMMEND").sum()) if not summary.empty else 0
    avg_final = float(summary["final"].mean()) if not summary.empty else 0.0
    avg_return = float(pd.to_numeric(summary["top1_max_return"], errors="coerce").fillna(0).mean()) if not summary.empty else 0.0
    worst_mdd = float(pd.to_numeric(summary["top1_mdd"], errors="coerce").fillna(0).min()) if not summary.empty else 0.0

    m1, m2, m3, m4 = st.columns(4)
    _metric(m1, "추천 통과", f"{recommend_count}개", "Decision = RECOMMEND")
    _metric(m2, "평균 Final", f"{avg_final:.2f}%", "Top1 similarity")
    _metric(m3, "평균 Replay 수익", f"{avg_return:+.2f}%", "Top1 historical max return", avg_return)
    _metric(m4, "최악 Replay MDD", f"{worst_mdd:.2f}%", "Top1 historical drawdown", worst_mdd)

    st.markdown("<div class='panel-title'>1. 오늘 추천종목 전체 요약</div>", unsafe_allow_html=True)
    st.dataframe(summary, use_container_width=True, hide_index=True)

    selected = st.selectbox(
        "상세 검증 종목",
        list(range(len(rows))),
        format_func=lambda i: f"#{i + 1} {rows[i].name or rows[i].ticker} · {rows[i].ticker}",
    )
    item = rows[selected]

    st.markdown(
        f"""
        <div class="replay-card">
          <div>
            <div class="eyebrow">RECOMMENDATION #{selected + 1}</div>
            <h2>{item.name or item.ticker} <small>{item.market.upper()}:{item.ticker}</small></h2>
          </div>
          <div class="replay-score">{_fmt(item.final_similarity)}%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    s1, s2, s3, s4, s5, s6 = st.columns(6)
    _metric(s1, "Decision", str(item.decision), "ADE decision")
    _metric(s2, "Final", f"{_fmt(item.final_similarity)}%", "Combined similarity")
    _metric(s3, "Weekly", f"{_fmt(item.weekly_similarity)}%", "Weekly shape")
    _metric(s4, "STO", f"{_fmt(item.sto_similarity)}%", "3-layer structure")
    _metric(s5, "Top1 Max Return", f"{_fmt(item.matched_max_return)}%", "Historical outcome")
    _metric(s6, "Top1 MDD", f"{_fmt(item.matched_max_drawdown)}%", "Historical risk")

    st.markdown("<div class='panel-title'>2. 추천 사유</div>", unsafe_allow_html=True)
    if item.reasons:
        for reason in item.reasons:
            st.markdown(f"- {reason}")
    else:
        st.info("저장된 추천 사유가 없습니다.")

    st.markdown("<div class='panel-title'>3. Top5 Replay 비교</div>", unsafe_allow_html=True)
    match_table = pd.DataFrame(
        [
            {
                "rank": f"Top {idx}",
                "event_id": match.event_id,
                "market": match.market.upper(),
                "ticker": match.ticker,
                "name": match.name,
                "final": match.final_similarity,
                "weekly": match.weekly_similarity,
                "sto": match.sto_similarity,
                "max_return": match.max_return,
                "mdd": match.max_drawdown,
                "same_as_now_week": match.equivalent_week_index,
                "future_weeks": match.future_weeks_available,
            }
            for idx, match in enumerate(item.replay_matches[:5], start=1)
        ]
    )
    st.dataframe(match_table, use_container_width=True, hide_index=True)

    if not item.replay_matches:
        st.warning("표시할 Replay 매치가 없습니다.")
        return

    st.markdown("<div class='panel-title'>4. 현재 차트 vs Replay 차트</div>", unsafe_allow_html=True)
    match_idx = st.selectbox(
        "차트로 확인할 Replay",
        list(range(min(5, len(item.replay_matches)))),
        format_func=lambda i: f"Top {i + 1} · {item.replay_matches[i].name or item.replay_matches[i].ticker} · {item.replay_matches[i].event_id}",
    )

    col_a, col_b = st.columns(2)
    generate_selected = col_a.button("선택 Replay 차트 생성")
    generate_all = col_b.button("Top5 차트 모두 생성")

    chart_key = f"{item.market}:{item.ticker}:{selected}"
    charts = st.session_state.setdefault("dashboard_report_charts", {})

    if generate_selected or generate_all:
        viewer = RecommendationChartViewer(db_path=db_path, output_dir="output/dashboard_report_charts")
        try:
            targets = range(min(5, len(item.replay_matches))) if generate_all else [match_idx]
            for idx in targets:
                chart_path = viewer.render_replay_match(item, item.replay_matches[idx], selected + 1, idx + 1)
                if chart_path:
                    charts[f"{chart_key}:{idx}"] = str(chart_path)
        finally:
            viewer.close()

    selected_path = charts.get(f"{chart_key}:{match_idx}")
    if selected_path and Path(selected_path).exists():
        st.image(selected_path, use_container_width=True)
    else:
        st.info("차트 생성 버튼을 누르면 현재 6개월 주봉과 Replay 이후 실제 흐름이 표시됩니다.")

    with st.expander("Top5 Replay 차트 전체 보기"):
        shown = False
        for idx, match in enumerate(item.replay_matches[:5]):
            path = charts.get(f"{chart_key}:{idx}")
            if path and Path(path).exists():
                st.markdown(f"**Top {idx + 1} · {match.name or match.ticker} · {match.event_id}**")
                st.image(path, use_container_width=True)
                shown = True
        if not shown:
            st.caption("Top5 차트 모두 생성 버튼을 누르면 이 영역에 전체 비교차트가 표시됩니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE Integrated Dashboard")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    _run(args.db)


if __name__ == "__main__":
    main()
