from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from dashboard.data import PaperDashboardData
from dashboard.design_system import StatusBadge, apply_design_system, page_header, section
from dashboard.paper_app import (
    _capital_timeline,
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


_STATUS_LABELS = {
    "IDLE": "대기",
    "RUNNING": "진행 중",
    "COMPLETED": "완료",
    "FAILED": "실패",
    "SUCCESS": "완료",
    "ERROR": "실패",
}


def _fmt(value: object, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.00"


def _status_label(value: object) -> str:
    raw = str(value or "IDLE").strip()
    return _STATUS_LABELS.get(raw.upper(), raw or "대기")


def _decision_label(value: object) -> str:
    raw = str(value or "-").strip()
    return {
        "RECOMMEND": "추천",
        "WATCH": "관찰",
        "HOLD": "보유",
        "REJECT": "제외",
    }.get(raw.upper(), raw or "-")


def _panel_title(st: object, title: str) -> None:
    st.markdown(f"<div class='panel-title'>{title}</div>", unsafe_allow_html=True)


def _run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 통합관제", page_icon="◈", layout="wide")
    apply_design_system(st)

    data = PaperDashboardData(db_path)
    try:
        metrics = data.metrics()
        positions = data.load_positions()
        orders = data.load_orders()
        curve = data.equity_curve()
    finally:
        data.close()

    page_header(
        "ADE 통합관제",
        "추천 생성·검증, 보유 판단, 모의주문 승인 현황을 한 화면에서 확인합니다.",
        eyebrow="ADE · 통합 투자 운영",
        badges=(StatusBadge("모의투자", "info"),),
    )

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    _metric(k1, "투자원금", f"{metrics.invested_amount:,.0f}원", "투입 원금")
    _metric(k2, "평가금액", f"{metrics.evaluation_amount:,.0f}원", "현재 평가액")
    _metric(k3, "평가손익", f"{metrics.pnl:,.0f}원", "미실현 손익", metrics.pnl)
    _metric(k4, "수익률", f"{metrics.pnl_rate:+.2f}%", "포트폴리오 수익률", metrics.pnl_rate)
    _metric(k5, "보유종목", f"{len(positions)}개", "현재 보유 수")
    _metric(k6, "수익 / 손실", f"{metrics.winners} / {metrics.losers}", "양수 / 음수 종목")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["종합 현황", "보유종목", "리플레이 분석", "주문 내역", "추천 검증", "매도 판단"]
    )

    with tab1:
        left, center, right = st.columns([1.05, 1.55, 1.0])
        with left:
            _panel_title(st, "포트폴리오 레이더")
            _portfolio_radar(st, positions)
            _panel_title(st, "주요 등락 종목")
            _top_movers(st, positions)
        with center:
            _panel_title(st, "자산 추이")
            _capital_timeline(st, curve)
            _panel_title(st, "보유종목 히트맵")
            _position_heatmap(st, positions)
        with right:
            _panel_title(st, "시스템 상태")
            _system_status(st, orders, positions)
            _panel_title(st, "최근 주문")
            _latest_orders_cards(st, orders)

    with tab2:
        _panel_title(st, "보유종목 현황")
        _positions_table(st, positions)

    with tab3:
        _panel_title(st, "리플레이 기준 모니터")
        _replay_basis(st, positions)

    with tab4:
        _panel_title(st, "주문 이력")
        _orders_table(st, orders)

    with tab5:
        _recommendation_report(st, db_path)

    with tab6:
        render_sell_panel(st, db_path, positions)

    st.caption("ADE 통합관제 · 매도는 자동 실행하지 않으며 사용자가 승인한 KIS 모의주문만 전송합니다.")


def _recommendation_report(st: object, db_path: str) -> None:
    section("추천 검증 보고서", "추천 사유와 과거 유사 사례를 함께 검증합니다.")
    st.info("현재 시점 추천종목을 생성·저장한 뒤 추천 사유와 상위 5개 리플레이 사례를 상세 검증합니다.")

    c1, c2, c3, c4 = st.columns(4)
    top_n = c1.number_input("추천 수", min_value=1, max_value=30, value=10, step=1, key="report_top_n")
    weekly_pool = c2.number_input("주간 후보군", min_value=20, max_value=300, value=100, step=10, key="report_pool")
    min_weekly = c3.number_input("주봉 유사도 기준", min_value=70.0, max_value=99.0, value=85.0, step=1.0, key="report_weekly")
    min_sto = c4.number_input("STO 유사도 기준", min_value=70.0, max_value=99.0, value=85.0, step=1.0, key="report_sto")

    manager = ADEJobManager()
    current_job = manager.current_status() or {}
    j1, j2, j3 = st.columns(3)
    j1.metric("ADE 작업 상태", _status_label(current_job.get("state")))
    j2.metric("현재 작업", str(current_job.get("job_name") or "없음"))
    j3.metric("최근 갱신", str(current_job.get("updated_at") or "없음"))

    generate_col, verify_col = st.columns(2)
    generate_clicked = generate_col.button(
        "추천종목 생성 및 저장",
        type="primary",
        use_container_width=True,
        key="generate_recommendations",
    )
    verify_clicked = verify_col.button(
        "추천 검증 보고서 생성",
        use_container_width=True,
        key="verify_recommendations",
    )

    if generate_clicked:
        with st.status("현재 시점 추천종목을 생성하고 있습니다.", expanded=True) as status:
            service = DailyRecommendationService(db_path)
            try:
                st.write("다른 데이터베이스 작업 종료 대기")
                with manager.acquire(
                    "MANUAL_RECOMMENDATION",
                    wait=True,
                    timeout_seconds=6 * 60 * 60,
                ):
                    st.write("리플레이 벡터와 주봉·STO 유사도 계산")
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
                    f"소요시간 {result.elapsed_seconds:.1f}초 · 실행 ID {result.run_id}"
                )
                st.caption(f"HTML 보고서: {result.report_path}")
            except Exception as exc:
                status.update(label="추천종목 생성 실패", state="error", expanded=True)
                st.error(str(exc))
            finally:
                service.close()

    if verify_clicked:
        with st.status("추천 검증 보고서를 계산하고 있습니다.", expanded=False) as status:
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
            status.update(label="추천 검증 보고서 생성 완료", state="complete")

    rows = st.session_state.get("dashboard_recommendation_report", [])
    if not rows:
        st.info("추천종목을 생성·저장하거나 추천 검증 보고서 생성 버튼을 눌러 주세요.")
        return

    summary = pd.DataFrame(
        [
            {
                "순위": idx,
                "시장": item.market.upper(),
                "종목코드": item.ticker,
                "종목명": item.name,
                "판정": _decision_label(item.decision),
                "종합 유사도": round(float(item.final_similarity), 2),
                "주봉 유사도": round(float(item.weekly_similarity), 2),
                "STO 유사도": round(float(item.sto_similarity), 2),
                "1순위 리플레이": item.matched_event_id,
                "1순위 최대수익률": item.matched_max_return,
                "1순위 최대낙폭": item.matched_max_drawdown,
                "최근 이벤트": item.recent_event_date,
                "최근 자금비율": item.recent_money_ratio,
            }
            for idx, item in enumerate(rows, start=1)
        ]
    )

    recommend_count = sum(1 for item in rows if str(item.decision).upper() == "RECOMMEND")
    avg_final = float(summary["종합 유사도"].mean()) if not summary.empty else 0.0
    avg_return = float(pd.to_numeric(summary["1순위 최대수익률"], errors="coerce").fillna(0).mean()) if not summary.empty else 0.0
    worst_mdd = float(pd.to_numeric(summary["1순위 최대낙폭"], errors="coerce").fillna(0).min()) if not summary.empty else 0.0

    m1, m2, m3, m4 = st.columns(4)
    _metric(m1, "추천 통과", f"{recommend_count}개", "추천 판정 통과")
    _metric(m2, "평균 종합 유사도", f"{avg_final:.2f}%", "상위 사례 유사도")
    _metric(m3, "평균 리플레이 수익", f"{avg_return:+.2f}%", "과거 최대수익률 평균", avg_return)
    _metric(m4, "최악 리플레이 낙폭", f"{worst_mdd:.2f}%", "과거 최대낙폭", worst_mdd)

    _panel_title(st, "1. 오늘의 추천종목 요약")
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
            <div class="ade-eyebrow">추천 #{selected + 1}</div>
            <h2>{item.name or item.ticker} <small>{item.market.upper()}:{item.ticker}</small></h2>
          </div>
          <div class="replay-score">{_fmt(item.final_similarity)}%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    s1, s2, s3, s4, s5, s6 = st.columns(6)
    _metric(s1, "판정", _decision_label(item.decision), "ADE 판정")
    _metric(s2, "종합 유사도", f"{_fmt(item.final_similarity)}%", "통합 유사도")
    _metric(s3, "주봉 유사도", f"{_fmt(item.weekly_similarity)}%", "주봉 형태")
    _metric(s4, "STO 유사도", f"{_fmt(item.sto_similarity)}%", "3계층 구조")
    _metric(s5, "1순위 최대수익률", f"{_fmt(item.matched_max_return)}%", "과거 성과")
    _metric(s6, "1순위 최대낙폭", f"{_fmt(item.matched_max_drawdown)}%", "과거 위험")

    _panel_title(st, "2. 추천 사유")
    if item.reasons:
        for reason in item.reasons:
            st.markdown(f"- {reason}")
    else:
        st.info("저장된 추천 사유가 없습니다.")

    _panel_title(st, "3. 상위 5개 리플레이 비교")
    match_rows = []
    for idx, match in enumerate(item.replay_matches, start=1):
        match_rows.append(
            {
                "순위": idx,
                "이벤트 ID": match.event_id,
                "종목명": match.name,
                "종목코드": match.ticker,
                "종합 유사도": match.final_similarity,
                "주봉 유사도": match.weekly_similarity,
                "STO 유사도": match.sto_similarity,
                "최대수익률": match.max_return,
                "최대낙폭": match.max_drawdown,
            }
        )
    st.dataframe(pd.DataFrame(match_rows), use_container_width=True, hide_index=True)

    if item.replay_matches:
        match_idx = st.selectbox(
            "차트로 볼 리플레이",
            list(range(len(item.replay_matches))),
            format_func=lambda i: f"상위 {i + 1} · {item.replay_matches[i].name or item.replay_matches[i].ticker}",
        )
        if st.button("비교 차트 다시 만들기"):
            chart_viewer = RecommendationChartViewer(db_path=db_path, output_dir="output/dashboard_charts")
            try:
                chart_path = chart_viewer.render_replay_match(
                    item,
                    item.replay_matches[match_idx],
                    selected + 1,
                    match_idx + 1,
                )
            finally:
                chart_viewer.close()
            st.session_state["dashboard_report_chart"] = chart_path
        chart_path = st.session_state.get("dashboard_report_chart")
        if chart_path and Path(chart_path).exists():
            st.image(chart_path, use_container_width=True)
        else:
            st.info("비교 차트 다시 만들기 버튼을 누르면 차트가 표시됩니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE 통합관제")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    _run(args.db)


if __name__ == "__main__":
    main()
