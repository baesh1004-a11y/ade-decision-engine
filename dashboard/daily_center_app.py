from __future__ import annotations

from pathlib import Path

import pandas as pd

from dashboard.system_status import inspect_market_db
from maintenance.recommendation_runner import cancel_job, get_status, start_job
from markets.profiles import get_market_profile
from recommendation.daily_service import DailyRecommendationService


def _render_diagnostics(st, diagnostics: dict[str, object]) -> None:
    if not diagnostics:
        return
    st.markdown("#### 단계별 분석 결과")
    rows = [
        ("과거 급등직전 패턴", diagnostics.get("patterns_loaded", 0), "선택 기간과 패턴 풀에 포함된 과거 정답 패턴"),
        ("정상 패턴", diagnostics.get("patterns_prepared", 0), "주봉·STO 데이터가 정상인 패턴"),
        ("분석 대상 종목", diagnostics.get("symbols_total", 0), "현재 활성화된 전체 종목"),
        ("120일 데이터 확보", diagnostics.get("symbols_with_120d", 0), "최근 120거래일 비교가 가능한 종목"),
        ("주봉 기준 통과", diagnostics.get("weekly_pass_comparisons", 0), "주봉 최소 유사도를 통과한 종목-패턴 비교"),
        ("STO 기준 통과", diagnostics.get("sto_pass_comparisons", 0), "STO 최소 유사도까지 통과한 종목-패턴 비교"),
        ("매칭 종목", diagnostics.get("symbols_with_matches", 0), "과거 급등직전 패턴과 하나 이상 매칭된 종목"),
        ("최종 추천", diagnostics.get("final_recommendations", 0), "최종 유사도 순으로 저장된 종목"),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["단계", "통과 수", "의미"]), use_container_width=True, hide_index=True)


def _render_selected_options(st, values: dict[str, object]) -> None:
    if not values:
        return
    years = values.get("candidate_years", values.get("replay_years", 2))
    pool = values.get("pattern_pool", values.get("weekly_pool_n", 100))
    weekly = float(values.get("min_weekly_similarity", 0) or 0)
    sto = float(values.get("min_sto_similarity", 0) or 0)
    st.caption(
        f"적용 기준 · 최근 {years}년 · 과거 패턴 {pool}개 · "
        f"주봉 {weekly:.0f}% 이상 · STO {sto:.0f}% 이상 · 최종점수 주봉 60% + STO 40%"
    )


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
          <div class="eyebrow">ADE {profile.code.upper()} PRE-SURGE RECOMMENDATION</div>
          <h1>{profile.name} 급등직전 120일 패턴 추천</h1>
          <p>현재 종목의 최근 120거래일을 과거 실제 30% 급등 직전 120거래일과 비교합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    service = DailyRecommendationService(profile.db_path)
    try:
        readiness = inspect_market_db(profile.db_path, profile.code)
        runs = service.latest_runs(50)
        latest_auto = next((row for row in runs if row["run_type"] == "AUTO"), None)
        latest_manual = next((row for row in runs if row["run_type"] == "MANUAL"), None)
        runtime = get_status(profile.code)

        a, b, c, d = st.columns(4)
        a.metric("운영 준비", "READY" if readiness.ready else "NOT READY")
        b.metric("활성 종목", f"{readiness.active_symbols:,}")
        c.metric("급등직전 패턴", f"{readiness.surge_patterns:,}")
        d.metric("가격 최신일", readiness.latest_price_date or "없음")

        if not readiness.ready:
            st.error("추천 실행 전 데이터 준비가 필요합니다: " + " / ".join(readiness.issues))

        st.markdown("### 운영 상태")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("자동 스케줄", profile.scheduler_time)
        s2.metric("오늘 자동 완료", "YES" if service.auto_completed_today() else "NO")
        s3.metric("현재 작업", str(runtime.get("stage", "없음")))
        s4.metric("작업 상태", str(runtime.get("state", "IDLE")))
        st.caption(f"최근 자동 {latest_auto['finished_at'] if latest_auto else '없음'} · 최근 수동 {latest_manual['finished_at'] if latest_manual else '없음'}")

        st.markdown("### 추천 기준")
        o1, o2, o3, o4 = st.columns(4)
        candidate_years = o1.number_input("과거 패턴 기간(년)", min_value=1, max_value=10, value=2, step=1, key=f"{profile.code}_replay_years")
        pattern_pool = o2.number_input("비교할 과거 패턴 수", min_value=10, max_value=1000, value=100, step=10, key=f"{profile.code}_weekly_pool")
        min_chart = o3.number_input("최소 주봉 유사도", min_value=0.0, max_value=100.0, value=85.0, step=1.0, key=f"{profile.code}_weekly")
        min_sto = o4.number_input("최소 STO 유사도", min_value=0.0, max_value=100.0, value=85.0, step=1.0, key=f"{profile.code}_sto")
        top_n = st.number_input("저장할 추천종목 수", min_value=1, max_value=50, value=20, step=1, key=f"{profile.code}_top_n")
        st.info("최종 유사도는 주봉 60% + STO 40%로 계산합니다. 급등 속도나 과거 수익률은 순위를 왜곡하지 않고 결과 설명에만 사용합니다.")

        running = bool(runtime.get("running"))
        start_col, refresh_col, stop_col = st.columns([4, 1.4, 1])
        if start_col.button(f"{profile.name} 추천종목 생성 및 저장", type="primary", use_container_width=True, key=f"{profile.code}_run", disabled=not readiness.ready or running):
            started = start_job(
                profile.code,
                profile.db_path,
                top_n=int(top_n),
                weekly_pool_n=int(pattern_pool),
                candidate_years=int(candidate_years),
                use_recent_replay=True,
                use_weekly_filter=True,
                min_weekly_similarity=float(min_chart),
                use_sto_filter=True,
                min_sto_similarity=float(min_sto),
            )
            if started:
                st.rerun()
            else:
                st.warning("이미 추천 작업이 실행 중입니다.")

        if refresh_col.button("진행상태 새로고침", use_container_width=True, key=f"{profile.code}_refresh"):
            st.rerun()

        if stop_col.button("⏹️ 중단", use_container_width=True, key=f"{profile.code}_cancel", disabled=not running):
            if cancel_job(profile.code):
                st.warning("중단 요청을 보냈습니다. 현재 비교 단위를 마친 뒤 안전하게 종료합니다.")
                st.rerun()

        live = get_status(profile.code)
        state = str(live.get("state", "IDLE"))
        if state in {"STARTING", "RUNNING", "CANCELLING"}:
            st.progress(float(live.get("progress", 0.0) or 0.0), text=str(live.get("message", "분석 중...")))
            current = int(live.get("current", 0) or 0)
            total = int(live.get("total", 0) or 0)
            p1, p2, p3 = st.columns(3)
            p1.metric("현재 단계", str(live.get("stage", "분석")))
            p2.metric("진행", f"{current:,} / {total:,}" if total else "준비 중")
            diagnostics = live.get("diagnostics") or {}
            p3.metric("현재 매칭 종목", f"{int(diagnostics.get('symbols_with_matches', 0)):,}")
            _render_selected_options(st, diagnostics)
            _render_diagnostics(st, diagnostics)
            st.caption("추천 계산은 백그라운드에서 계속 진행됩니다. 진행상태 새로고침 버튼으로 확인하세요.")
        elif state == "COMPLETED":
            st.success(f"추천 완료 및 저장 · {int(live.get('recommendation_count', 0))}개 · {float(live.get('elapsed_seconds', 0.0)):.1f}초")
            _render_selected_options(st, live.get("diagnostics") or {})
            _render_diagnostics(st, live.get("diagnostics") or {})
        elif state == "CANCELLED":
            st.warning("추천 생성이 사용자 요청으로 중단되었습니다.")
            _render_diagnostics(st, live.get("diagnostics") or {})
        elif state == "FAILED":
            st.error(str(live.get("error_message") or "추천 생성에 실패했습니다."))

        st.divider()
        st.markdown("### 저장된 추천 이력")
        runs = service.latest_runs(50)
        if not runs:
            st.info(f"{profile.name}에 저장된 추천 실행 이력이 없습니다.")
            return

        run_df = pd.DataFrame([{key: value for key, value in row.items() if key not in {"diagnostics", "parameters"}} for row in runs])
        st.dataframe(run_df, use_container_width=True, hide_index=True, column_config={
            "elapsed_seconds": st.column_config.NumberColumn("소요시간", format="%.1f초"),
            "recommendation_count": st.column_config.NumberColumn("추천 수", format="%d개"),
        })

        selectable = [row for row in runs if row["status"] in {"COMPLETED", "CANCELLED"}]
        if selectable:
            labels = {row["run_id"]: f"{row['started_at']} · {row['run_type']} · {row['status']} · {row['recommendation_count']}개" for row in selectable}
            selected = st.selectbox("상세 추천 결과", options=list(labels), format_func=lambda run_id: labels[run_id], key=f"{profile.code}_detail_run")
            selected_run = next(row for row in selectable if row["run_id"] == selected)
            _render_selected_options(st, selected_run.get("diagnostics") or selected_run.get("parameters") or {})
            _render_diagnostics(st, selected_run.get("diagnostics") or {})
            details = pd.DataFrame(service.recommendations_for_run(selected))
            if not details.empty:
                st.dataframe(details, use_container_width=True, hide_index=True)
                st.page_link("pages/13_Surge_Pattern_Lab.py", label="선택 추천 결과 차트 비교")
            report_path = selected_run.get("report_path")
            if report_path and Path(str(report_path)).exists():
                st.caption(f"HTML 보고서: {report_path}")
    finally:
        service.close()


if __name__ == "__main__":
    run("kr")
