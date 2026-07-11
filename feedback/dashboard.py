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
            <p>Meta Score 당시 예측을 저장하고, 7거래일 실제 결과와 비교합니다.</p>
          </div>
          <div class="badge">PREDICT → OBSERVE → VERIFY</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    engine = FeedbackEngine(db_path)
    try:
        c1, c2 = st.columns([1, 3])
        if c1.button("성과 업데이트", type="primary"):
            completed = engine.update_open_cases()
            st.success(f"새롭게 완료된 7일 평가: {completed}건")
        c2.caption("가격 DB에 새 거래일 데이터가 들어온 뒤 실행하면 OPEN 사례의 일별 성과와 7일 평가를 갱신합니다.")

        summary = engine.summary()
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("전체 사례", summary.total)
        k2.metric("7일 완료", summary.completed)
        k3.metric("성공", summary.success_count)
        k4.metric("적중률", f"{summary.hit_rate:.1f}%")
        k5.metric("평균 7일 수익", f"{summary.avg_7d_return:+.2f}%")
        k6.metric("평균 예측오차", f"{summary.avg_prediction_error:.2f}%p")

        tab1, tab2, tab3, tab4 = st.tabs(["전체 사례", "Meta 구간 검증", "요소별 검증", "개별 경로"])

        cases = engine.cases_dataframe()
        with tab1:
            if cases.empty:
                st.info("아직 저장된 Meta Score 사례가 없습니다. Meta Score 대시보드에서 통합점수를 계산하면 자동 저장됩니다.")
            else:
                display_cols = [
                    "snapshot_date", "market", "ticker", "name", "decision", "grade", "meta_score",
                    "predicted_7d_return", "actual_7d_return", "actual_max_return", "actual_min_return",
                    "predicted_peak_day", "actual_peak_day", "success", "status",
                ]
                st.dataframe(cases[[c for c in display_cols if c in cases.columns]], use_container_width=True, hide_index=True)

        with tab2:
            meta_stats = engine.bucket_stats("meta_score", BUCKETS)
            st.markdown("### Meta Score 구간별 적중률")
            st.dataframe(meta_stats, use_container_width=True, hide_index=True)
            if not meta_stats.empty:
                chart = meta_stats.set_index("bucket")[["hit_rate", "avg_7d_return"]]
                st.bar_chart(chart, height=360)

        with tab3:
            selected_factor = st.selectbox(
                "검증 요소",
                ["replay_score", "prediction_score", "jp_radar_score", "risk_score"],
                format_func=lambda x: {
                    "replay_score": "Replay",
                    "prediction_score": "Prediction",
                    "jp_radar_score": "JP Radar",
                    "risk_score": "Risk",
                }[x],
            )
            factor_stats = engine.bucket_stats(selected_factor, BUCKETS)
            st.dataframe(factor_stats, use_container_width=True, hide_index=True)
            if not factor_stats.empty:
                st.bar_chart(factor_stats.set_index("bucket")[["hit_rate", "avg_7d_return"]], height=360)

        with tab4:
            if cases.empty:
                st.info("표시할 사례가 없습니다.")
            else:
                options = list(cases.index)
                selected = st.selectbox(
                    "사례 선택",
                    options,
                    format_func=lambda i: f"{cases.loc[i, 'snapshot_date']} · {cases.loc[i, 'name'] or cases.loc[i, 'ticker']} · Meta {cases.loc[i, 'meta_score']:.2f}",
                )
                row = cases.loc[selected]
                daily = engine.daily_dataframe(int(row["id"]))
                d1, d2, d3, d4 = st.columns(4)
                d1.metric("예상 7일 수익", "-" if pd.isna(row.get("predicted_7d_return")) else f"{float(row['predicted_7d_return']):+.2f}%")
                d2.metric("실제 7일 수익", "-" if pd.isna(row.get("actual_7d_return")) else f"{float(row['actual_7d_return']):+.2f}%")
                d3.metric("예상 최고일", "-" if pd.isna(row.get("predicted_peak_day")) else f"{float(row['predicted_peak_day']):.1f}일")
                d4.metric("실제 최고일", "-" if pd.isna(row.get("actual_peak_day")) else f"{int(row['actual_peak_day'])}일")
                if daily.empty:
                    st.caption("아직 일별 가격 결과가 없습니다.")
                else:
                    st.line_chart(daily.set_index("day_no")["return_rate"], height=360)
                    st.dataframe(daily, use_container_width=True, hide_index=True)

        st.caption("성공 기준: 추천 시점 종가 대비 7거래일 종가 수익률이 0% 초과")
    finally:
        engine.close()


def _style(st: object) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#edf4ff);color:#15283b}
        .block-container{max-width:1600px;padding-top:1.25rem}
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
