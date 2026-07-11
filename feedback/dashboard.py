from __future__ import annotations

import argparse

import pandas as pd

from feedback.engine import FeedbackEngine


BUCKETS = [
    ("95~100", 95.0, 100.01),
    ("90~95", 90.0, 95.0),
    ("85~90", 85.0, 90.0),
    ("80~85", 80.0, 85.0),
    ("75~80", 75.0, 80.0),
    ("60~75", 60.0, 75.0),
    ("0~60", 0.0, 60.0),
]


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE Feedback", page_icon="↻", layout="wide")
    _style(st)

    st.markdown(
        """
        <div class="hero">
          <div>
            <div class="eyebrow">ADE PERFORMANCE VALIDATION</div>
            <h1>Feedback Dashboard</h1>
            <p>추천 이후 실제 성과를 매일 기록하고 종목별·점수별 통계로 검증합니다.</p>
          </div>
          <div class="badge">DAILY TRACK → ANALYZE → VERIFY</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    engine = FeedbackEngine(db_path)
    try:
        c1, c2 = st.columns([1, 3])
        if c1.button("오늘 성과 업데이트", type="primary"):
            result = engine.update_open_cases()
            st.success(
                f"대상 {result['updated_cases']}건 · 신규 일별기록 {result['inserted_days']}건 · 7일 완료 {result['completed']}건"
            )
        c2.caption("가격 DB가 갱신된 뒤 실행하면 모든 OPEN 추천의 최신 일별 성과를 저장합니다.")

        summary = engine.summary()
        k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
        k1.metric("전체 사례", summary.total)
        k2.metric("추적 중", summary.open_count)
        k3.metric("7일 완료", summary.completed)
        k4.metric("적중률", f"{summary.hit_rate:.1f}%")
        k5.metric("현재 평균수익", f"{summary.avg_current_return:+.2f}%")
        k6.metric("평균 7일수익", f"{summary.avg_7d_return:+.2f}%")
        k7.metric("평균 예측오차", f"{summary.avg_prediction_error:.2f}%p")

        cases = engine.cases_dataframe()
        ticker_stats = engine.ticker_statistics()
        tab1, tab2, tab3, tab4 = st.tabs(["Live Tracking", "History", "Statistics", "Insights"])

        with tab1:
            live = cases[cases["status"] == "OPEN"].copy() if not cases.empty else pd.DataFrame()
            if live.empty:
                st.info("현재 추적 중인 추천 사례가 없습니다.")
            else:
                live_cols = [
                    "snapshot_date", "market", "ticker", "name", "meta_score", "latest_day_no",
                    "current_return", "running_max_return", "running_min_return", "drawdown_from_peak",
                    "target_return", "stop_return", "target_hit", "stop_hit",
                ]
                st.dataframe(live[[c for c in live_cols if c in live.columns]], use_container_width=True, hide_index=True)

                selected = st.selectbox(
                    "추적 종목",
                    list(live.index),
                    format_func=lambda i: f"{live.loc[i, 'name'] or live.loc[i, 'ticker']} · D{int(live.loc[i, 'latest_day_no'] or 0)} · {float(live.loc[i, 'current_return'] or 0):+.2f}%",
                    key="live_case",
                )
                row = live.loc[selected]
                daily = engine.daily_dataframe(int(row["id"]))
                a, b, c, d, e = st.columns(5)
                a.metric("현재수익", f"{float(row.get('current_return') or 0):+.2f}%")
                b.metric("최고수익", f"{float(row.get('running_max_return') or 0):+.2f}%")
                c.metric("최저수익", f"{float(row.get('running_min_return') or 0):+.2f}%")
                d.metric("고점대비 낙폭", f"{float(row.get('drawdown_from_peak') or 0):+.2f}%")
                e.metric("진행일", f"D{int(row.get('latest_day_no') or 0)}")
                if not daily.empty:
                    chart = daily.set_index("day_no")[["return_rate", "running_max_return", "drawdown_from_peak"]]
                    st.line_chart(chart, height=420)
                    st.dataframe(daily, use_container_width=True, hide_index=True)

        with tab2:
            if cases.empty:
                st.info("저장된 추천 사례가 없습니다.")
            else:
                history_cols = [
                    "snapshot_date", "market", "ticker", "name", "decision", "grade", "meta_score",
                    "predicted_7d_return", "current_return", "actual_7d_return", "actual_max_return",
                    "actual_min_return", "predicted_peak_day", "actual_peak_day", "success", "status",
                ]
                st.dataframe(cases[[c for c in history_cols if c in cases.columns]], use_container_width=True, hide_index=True)

                selected = st.selectbox(
                    "이력 상세",
                    list(cases.index),
                    format_func=lambda i: f"{cases.loc[i, 'snapshot_date']} · {cases.loc[i, 'name'] or cases.loc[i, 'ticker']} · Meta {cases.loc[i, 'meta_score']:.2f}",
                    key="history_case",
                )
                row = cases.loc[selected]
                daily = engine.daily_dataframe(int(row["id"]))
                if not daily.empty:
                    st.line_chart(daily.set_index("day_no")["return_rate"], height=360)
                    st.dataframe(daily, use_container_width=True, hide_index=True)

        with tab3:
            st.markdown("### 종목별 장기 통계")
            if ticker_stats.empty:
                st.info("통계를 계산할 종목 데이터가 없습니다.")
            else:
                display = ticker_stats.copy()
                st.dataframe(display, use_container_width=True, hide_index=True)

                metric = st.selectbox(
                    "종목 비교 기준",
                    ["hit_rate", "avg_7d_return", "avg_max_return", "avg_min_return", "recommendation_count"],
                    format_func=lambda x: {
                        "hit_rate": "적중률",
                        "avg_7d_return": "평균 7일수익",
                        "avg_max_return": "평균 최고수익",
                        "avg_min_return": "평균 최저수익",
                        "recommendation_count": "추천 횟수",
                    }[x],
                )
                chart = display.sort_values(metric, ascending=False).head(15).set_index("name")[[metric]]
                st.bar_chart(chart, horizontal=True, height=500)

                factor = st.selectbox(
                    "점수 구간 검증",
                    ["meta_score", "replay_score", "prediction_score", "jp_radar_score", "risk_score"],
                    format_func=lambda x: {
                        "meta_score": "Meta",
                        "replay_score": "Replay",
                        "prediction_score": "Prediction",
                        "jp_radar_score": "JP Radar",
                        "risk_score": "Risk",
                    }[x],
                )
                factor_stats = engine.bucket_stats(factor, BUCKETS)
                st.dataframe(factor_stats, use_container_width=True, hide_index=True)
                if not factor_stats.empty:
                    st.bar_chart(factor_stats.set_index("bucket")[["hit_rate", "avg_7d_return"]], height=360)

        with tab4:
            st.markdown("### 자동 인사이트")
            for text in engine.insights():
                st.info(text)

            if not ticker_stats.empty:
                eligible = ticker_stats[ticker_stats["completed_count"] >= 1].copy()
                if not eligible.empty:
                    st.markdown("### 종목별 적중률 vs 평균수익")
                    st.scatter_chart(
                        eligible,
                        x="hit_rate",
                        y="avg_7d_return",
                        size="recommendation_count",
                        color="name",
                        height=460,
                    )

        st.caption("성공 기준: 추천 시점 종가 대비 7거래일 종가 수익률이 0% 초과")
    finally:
        engine.close()


def _style(st: object) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#edf4ff);color:#15283b}
        .block-container{max-width:1650px;padding-top:1.25rem}
        .hero{display:flex;justify-content:space-between;align-items:center;padding:24px 28px;border-radius:26px;background:rgba(255,255,255,.84);border:1px solid rgba(72,145,210,.22);box-shadow:0 18px 48px rgba(64,106,147,.12);margin-bottom:16px}
        .hero h1{margin:3px 0;letter-spacing:-.04em}.hero p{margin:5px 0;color:#687d92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}.badge{padding:11px 15px;border-radius:999px;background:#eaf4ff;color:#286ba6;font-weight:800}
        @media(max-width:768px){.block-container{padding:.75rem}.hero{display:block;padding:18px}.badge{display:inline-block;margin-top:12px}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE Feedback Dashboard")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
