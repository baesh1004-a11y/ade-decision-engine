from __future__ import annotations

import argparse

import pandas as pd

from feedback.engine import FeedbackEngine
from meta_score.engine import MetaScoreEngine
from recommendation.event_recommender import RecentMoneyEventRecommender


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE Meta Score", page_icon="◎", layout="wide")
    _style(st)

    st.markdown(
        """
        <div class="hero">
          <div>
            <div class="eyebrow">ADE FINAL DECISION LAYER</div>
            <h1>Meta Score Dashboard</h1>
            <p>Replay · Prediction · JP Radar · Market · Sector · Risk를 고정 가중치로 통합합니다.</p>
          </div>
          <div class="formula">30% · 25% · 20% · 10% · 10% · 5%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1, 2])
    top_n = c1.number_input("후보 수", min_value=3, max_value=30, value=10, step=1)
    replay_top = c2.number_input("Replay 표본", min_value=3, max_value=10, value=5, step=1)
    run_button = c3.button("통합점수 계산", type="primary")

    if run_button or "meta_score_results" not in st.session_state:
        with st.spinner("ADE 추천과 JP Radar를 결합해 통합점수를 계산 중..."):
            recommender = RecentMoneyEventRecommender(db_path=db_path)
            try:
                recommendations = recommender.recommend(top_n=int(top_n), replay_top_n=int(replay_top))
            finally:
                recommender.close()
            results = MetaScoreEngine().score(recommendations)
            st.session_state["meta_score_results"] = results

            feedback = FeedbackEngine(db_path)
            try:
                inserted = feedback.register_meta_results(results)
            finally:
                feedback.close()
            st.session_state["meta_feedback_inserted"] = inserted

    results = st.session_state.get("meta_score_results", [])
    if not results:
        st.info("통합점수 계산 결과가 없습니다.")
        return

    inserted = st.session_state.get("meta_feedback_inserted", 0)
    if inserted:
        st.success(f"오늘의 Meta Score {inserted}건을 Feedback DB에 저장했습니다.")

    final_buy = sum(1 for item in results if item.decision == "FINAL BUY")
    buy_watch = sum(1 for item in results if item.decision == "BUY WATCH")
    avg_score = sum(item.meta_score for item in results) / len(results)
    best = results[0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("최종 매수", final_buy)
    k2.metric("매수 관찰", buy_watch)
    k3.metric("평균 Meta", f"{avg_score:.2f}")
    k4.metric("1위", best.name or best.ticker, f"{best.meta_score:.2f} · {best.grade}")

    ranking = pd.DataFrame(
        [
            {
                "rank": item.rank,
                "market": item.market_code.upper(),
                "ticker": item.ticker,
                "name": item.name,
                "decision": item.decision,
                "grade": item.grade,
                "meta": item.meta_score,
                "replay": item.breakdown.replay,
                "prediction": item.breakdown.prediction,
                "jp_radar": item.breakdown.jp_radar,
                "market_score": item.breakdown.market,
                "sector_score": item.breakdown.sector,
                "risk": item.breakdown.risk,
                "7d_up": item.seven_day_up_probability,
                "7d_expected": item.seven_day_expected_return,
                "peak_day": item.expected_peak_day,
            }
            for item in results
        ]
    )

    st.markdown("### 최종 순위")
    st.dataframe(
        ranking,
        use_container_width=True,
        hide_index=True,
        column_config={
            "meta": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.2f"),
            "replay": st.column_config.NumberColumn(format="%.2f"),
            "prediction": st.column_config.NumberColumn(format="%.2f"),
            "jp_radar": st.column_config.NumberColumn(format="%.2f"),
            "7d_up": st.column_config.NumberColumn(format="%.1f%%"),
            "7d_expected": st.column_config.NumberColumn(format="%+.2f%%"),
        },
    )

    selected = st.selectbox(
        "상세 종목",
        list(range(len(results))),
        format_func=lambda i: f"#{results[i].rank} {results[i].name or results[i].ticker} · {results[i].meta_score:.2f}",
    )
    item = results[selected]

    st.markdown(
        f"""
        <div class="decision-card">
          <div><div class="eyebrow">FINAL DECISION #{item.rank}</div><h2>{item.name or item.ticker}</h2>
          <p>{item.market_code.upper()}:{item.ticker} · {item.jp_radar_signal}</p></div>
          <div class="score">{item.meta_score:.2f}<small>{item.grade} · {item.decision}</small></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    score_frame = pd.DataFrame(
        {
            "factor": ["Replay", "Prediction", "JP Radar", "Market", "Sector", "Risk"],
            "score": [
                item.breakdown.replay,
                item.breakdown.prediction,
                item.breakdown.jp_radar,
                item.breakdown.market,
                item.breakdown.sector,
                item.breakdown.risk,
            ],
        }
    )
    st.bar_chart(score_frame.set_index("factor"), horizontal=True, height=320)

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("7일 상승확률", "-" if item.seven_day_up_probability is None else f"{item.seven_day_up_probability:.1f}%")
    p2.metric("7일 기대수익", "-" if item.seven_day_expected_return is None else f"{item.seven_day_expected_return:+.2f}%")
    p3.metric("예상 최고점", "-" if item.expected_peak_day is None else f"{item.expected_peak_day:.1f}일")
    p4.metric("목표 / 손절", f"{item.target_return if item.target_return is not None else '-'} / {item.stop_return if item.stop_return is not None else '-'}")

    st.markdown("### 판단 근거")
    for reason in item.reasons:
        st.markdown(f"- {reason}")

    st.caption("고정 공식: Replay 30% + Prediction 25% + JP Radar 20% + Market 10% + Sector 10% + Risk 5%")


def _style(st: object) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#f9fbff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1600px;padding-top:1.3rem}
        .hero,.decision-card{display:flex;justify-content:space-between;align-items:center;padding:24px 28px;border:1px solid rgba(76,145,207,.23);border-radius:26px;background:rgba(255,255,255,.82);box-shadow:0 18px 50px rgba(63,105,145,.12);margin-bottom:16px}
        .hero h1,.decision-card h2{margin:3px 0;letter-spacing:-.04em}.hero p,.decision-card p{margin:5px 0;color:#647b92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        .formula{padding:12px 16px;border-radius:999px;background:#eaf4ff;color:#286ba6;font-weight:800}.score{font-size:46px;font-weight:900;color:#0e6fc4;text-align:right}.score small{display:block;font-size:14px;color:#5f758b}
        @media(max-width:768px){.block-container{padding:.75rem}.hero,.decision-card{display:block;padding:18px}.score{text-align:left;margin-top:12px;font-size:38px}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE Meta Score Dashboard")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
