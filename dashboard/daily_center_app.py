from __future__ import annotations

from pathlib import Path

import pandas as pd

from maintenance.job_manager import ADEJobManager
from markets.profiles import get_market_profile
from recommendation.daily_service import DailyRecommendationService


def run(market_code: str = "kr") -> None:
    import streamlit as st

    profile = get_market_profile(market_code)
    st.set_page_config(page_title=f"ADE {profile.name} Daily Center", page_icon="📅", layout="wide")
    st.markdown(
        f"""
        <style>
        :root{{--ink:#14263a;--muted:#6d8194;--line:rgba(77,125,168,.18);--blue:#2f80ed}}
        .stApp{{background:radial-gradient(circle at 12% 0%,rgba(125,190,255,.20),transparent 27%),linear-gradient(135deg,#f7fbff,#eef5fb 52%,#f9fcff);color:var(--ink)}}
        .block-container{{max-width:1540px;padding-top:1.05rem;padding-bottom:3rem}}
        [data-testid="stSidebar"]{{background:linear-gradient(180deg,rgba(248,252,255,.97),rgba(232,242,251,.98));border-right:1px solid var(--line)}}
        [data-testid="stSidebar"] a{{border-radius:12px;margin:3px 8px;padding:9px 12px;color:#30475d!important;font-weight:650}}
        [data-testid="stSidebar"] a:hover{{background:rgba(47,128,237,.08)}}
        [data-testid="stSidebar"] a[aria-current="page"]{{background:linear-gradient(135deg,#dcecff,#eef6ff);color:#1768bd!important;box-shadow:inset 0 0 0 1px rgba(47,128,237,.16)}}
        .hero{{padding:30px 34px;border-radius:28px;background:linear-gradient(135deg,rgba(255,255,255,.94),rgba(240,248,255,.86));border:1px solid var(--line);box-shadow:0 22px 62px rgba(42,88,130,.12);margin-bottom:20px;position:relative;overflow:hidden}}
        .hero:after{{content:"";position:absolute;right:-60px;top:-90px;width:260px;height:260px;border-radius:50%;background:radial-gradient(circle,rgba(67,149,236,.20),rgba(67,149,236,0) 68%)}}
        .hero h1{{margin:5px 0 7px;font-size:36px;letter-spacing:-.045em;line-height:1.12}}
        .hero p{{margin:0;color:var(--muted);font-size:15px}}
        .eyebrow{{font-size:12px;letter-spacing:.16em;font-weight:850;color:#2f78ba}}
        div[data-testid="stMetric"]{{background:rgba(255,255,255,.78);border:1px solid var(--line);padding:16px 18px;border-radius:18px;box-shadow:0 9px 26px rgba(56,100,139,.07)}}
        div[data-testid="stMetricLabel"]{{color:#6e8295;font-weight:700}}
        div[data-testid="stMetricValue"]{{font-size:1.8rem;font-weight:850;letter-spacing:-.035em;color:#1b334a}}
        h3{{margin-top:1.65rem!important;margin-bottom:.75rem!important;letter-spacing:-.03em;color:#1c344c}}
        div[data-baseweb="input"]>div,div[data-baseweb="select"]>div{{border-radius:13px!important;background:rgba(255,255,255,.88)!important;border-color:var(--line)!important}}
        div[data-testid="stButton"] button{{border-radius:14px;min-height:46px;font-weight:800;letter-spacing:-.015em;border:1px solid rgba(47,128,237,.18)}}
        div[data-testid="stDataFrame"]{{border-radius:18px;overflow:hidden;border:1px solid var(--line);box-shadow:0 10px 28px rgba(56,100,139,.07)}}
        div[data-testid="stAlert"]{{border-radius:16px}}
        hr{{border-color:var(--line)!important}}
        @media(max-width:768px){{.block-container{{padding:.75rem}}.hero{{padding:22px}}.hero h1{{font-size:29px}}}}
        </style>
        <div class="hero">
          <div class="eyebrow">ADE {profile.code.upper()} DAILY RECOMMENDATION CENTER</div>
          <h1>{profile.name} 자동·수동 추천 운영</h1>
          <p>DB {profile.db_path} · 가격원 {profile.price_source} · 통화 {profile.currency}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    service = DailyRecommendationService(profile.db_path)
    manager = ADEJobManager(status_path=f"output/{profile.code}_job_status.json")
    try:
        runs = service.latest_runs(50)
        latest_auto = next((row for row in runs if row["run_type"] == "AUTO"), None)
        latest_manual = next((row for row in runs if row["run_type"] == "MANUAL"), None)
        job_status = manager.current_status() or {}

        a, b, c, d = st.columns(4)
        a.metric("자동 스케줄", profile.scheduler_time)
        b.metric("오늘 자동 완료", "YES" if service.auto_completed_today() else "NO")
        c.metric("최근 자동", latest_auto["finished_at"] if latest_auto else "없음")
        d.metric("최근 수동", latest_manual["finished_at"] if latest_manual else "없음")

        st.markdown("### ADE 작업 상태")
        s1, s2, s3 = st.columns(3)
        s1.metric("상태", str(job_status.get("state", "IDLE")))
        s2.metric("작업", str(job_status.get("job_name", "없음")))
        s3.metric("갱신", str(job_status.get("updated_at", "없음")))

        if not profile.db_path.exists():
            st.warning(f"{profile.db_path}가 없습니다. 해당 시장 DB를 먼저 구축해야 합니다.")

        st.markdown("### 장중 수동 추천")
        c1, c2, c3, c4 = st.columns(4)
        top_n = c1.number_input("추천 개수", min_value=1, max_value=50, value=20, step=1, key=f"{profile.code}_top_n")
        weekly_pool = c2.number_input("주봉 후보", min_value=10, max_value=300, value=100, step=10, key=f"{profile.code}_weekly_pool")
        min_weekly = c3.number_input("최소 주봉 유사도", min_value=0.0, max_value=100.0, value=85.0, step=1.0, key=f"{profile.code}_weekly")
        min_sto = c4.number_input("최소 STO 유사도", min_value=0.0, max_value=100.0, value=85.0, step=1.0, key=f"{profile.code}_sto")

        if st.button(f"{profile.name} 현재 시점 추천종목 생성", type="primary", use_container_width=True, key=f"{profile.code}_run"):
            with st.status(f"{profile.name} 수동 추천을 작업 대기열에 등록했습니다...", expanded=True) as status:
                try:
                    with manager.acquire(
                        f"{profile.code.upper()}_MANUAL_RECOMMENDATION",
                        wait=True,
                        timeout_seconds=6 * 60 * 60,
                    ):
                        result = service.run(
                            "MANUAL",
                            top_n=int(top_n),
                            weekly_pool_n=int(weekly_pool),
                            min_weekly_similarity=float(min_weekly),
                            min_sto_similarity=float(min_sto),
                        )
                    status.update(label="수동 추천 생성 완료", state="complete", expanded=False)
                    st.success(f"{result.recommendation_count}개 추천 · {result.elapsed_seconds:.1f}초 · {result.run_id}")
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
            st.info(f"{profile.name}에 저장된 추천 실행 이력이 없습니다.")
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
                key=f"{profile.code}_detail_run",
            )
            details = pd.DataFrame(service.recommendations_for_run(selected))
            if not details.empty:
                st.dataframe(details, use_container_width=True, hide_index=True)
    finally:
        service.close()


if __name__ == "__main__":
    run("kr")
