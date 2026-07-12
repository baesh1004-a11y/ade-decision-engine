from __future__ import annotations

from pathlib import Path

import pandas as pd

from maintenance.job_manager import ADEJobManager
from recommendation.daily_service import DailyRecommendationService


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE Daily Center", page_icon="📅", layout="wide")
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#fbfdff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1550px;padding-top:1.1rem}
        .hero{padding:24px 28px;border-radius:26px;background:rgba(255,255,255,.86);border:1px solid rgba(72,145,210,.22);box-shadow:0 18px 48px rgba(64,106,147,.12);margin-bottom:16px}
        .hero h1{margin:3px 0}.hero p{margin:5px 0;color:#687d92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        </style>
        <div class="hero">
          <div class="eyebrow">ADE DAILY RECOMMENDATION CENTER</div>
          <h1>자동·수동 추천 운영</h1>
          <p>평일 16:10 자동 추천과 장중 수동 추천이 동일한 엔진과 동일한 DB 이력을 사용합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    service = DailyRecommendationService()
    manager = ADEJobManager()
    try:
        runs = service.latest_runs(50)
        latest_auto = next((row for row in runs if row["run_type"] == "AUTO"), None)
        latest_manual = next((row for row in runs if row["run_type"] == "MANUAL"), None)
        job_status = manager.current_status() or {}

        a, b, c, d = st.columns(4)
        a.metric("자동 스케줄", "평일 16:10")
        b.metric("오늘 자동 완료", "YES" if service.auto_completed_today() else "NO")
        c.metric("최근 자동", latest_auto["finished_at"] if latest_auto else "없음")
        d.metric("최근 수동", latest_manual["finished_at"] if latest_manual else "없음")

        st.markdown("### ADE 작업 상태")
        s1, s2, s3 = st.columns(3)
        s1.metric("상태", str(job_status.get("state", "IDLE")))
        s2.metric("작업", str(job_status.get("job_name", "없음")))
        s3.metric("갱신", str(job_status.get("updated_at", "없음")))

        st.markdown("### 장중 수동 추천")
        c1, c2, c3, c4 = st.columns(4)
        top_n = c1.number_input("추천 개수", min_value=1, max_value=50, value=20, step=1)
        weekly_pool = c2.number_input("주봉 후보", min_value=10, max_value=300, value=100, step=10)
        min_weekly = c3.number_input("최소 주봉 유사도", min_value=0.0, max_value=100.0, value=85.0, step=1.0)
        min_sto = c4.number_input("최소 STO 유사도", min_value=0.0, max_value=100.0, value=85.0, step=1.0)

        if st.button("현재 시점 추천종목 생성", type="primary", use_container_width=True):
            with st.status("수동 추천을 작업 대기열에 등록했습니다...", expanded=True) as status:
                try:
                    st.write("다른 DB 작업이 끝날 때까지 대기")
                    with manager.acquire(
                        "MANUAL_RECOMMENDATION",
                        wait=True,
                        timeout_seconds=6 * 60 * 60,
                    ):
                        st.write("Replay Vector 후보 축소")
                        st.write("주봉·STO 슬라이딩 매칭")
                        st.write("Prediction 계산 및 결과 저장")
                        result = service.run(
                            "MANUAL",
                            top_n=int(top_n),
                            weekly_pool_n=int(weekly_pool),
                            min_weekly_similarity=float(min_weekly),
                            min_sto_similarity=float(min_sto),
                        )
                    status.update(label="수동 추천 생성 완료", state="complete", expanded=False)
                    st.success(
                        f"{result.recommendation_count}개 추천 · "
                        f"{result.elapsed_seconds:.1f}초 · {result.run_id}"
                    )
                    if Path(result.report_path).exists():
                        st.caption(f"HTML 보고서: {result.report_path}")
                    st.rerun()
                except Exception as exc:
                    status.update(label="수동 추천 실패", state="error", expanded=True)
                    st.error(str(exc))

        st.divider()
        st.markdown("### 추천 생성 이력")
        runs = service.latest_runs(50)
        if not runs:
            st.info("아직 저장된 추천 실행 이력이 없습니다.")
            return

        run_df = pd.DataFrame(runs)
        st.dataframe(
            run_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "elapsed_seconds": st.column_config.NumberColumn("소요시간", format="%.1f초"),
                "recommendation_count": st.column_config.NumberColumn("추천 수", format="%d개"),
            },
        )

        completed = [row for row in runs if row["status"] == "COMPLETED"]
        if completed:
            labels = {
                row["run_id"]: f"{row['started_at']} · {row['run_type']} · {row['recommendation_count']}개"
                for row in completed
            }
            selected = st.selectbox(
                "상세 추천 결과",
                options=list(labels),
                format_func=lambda run_id: labels[run_id],
            )
            details = pd.DataFrame(service.recommendations_for_run(selected))
            if not details.empty:
                st.dataframe(details, use_container_width=True, hide_index=True)
    finally:
        service.close()


if __name__ == "__main__":
    run()
