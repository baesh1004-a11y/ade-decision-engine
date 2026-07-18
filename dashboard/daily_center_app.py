from __future__ import annotations

from pathlib import Path

import pandas as pd

from dashboard.system_status import inspect_market_db
from maintenance.recommendation_runner import cancel_job, get_status, start_job
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, display_symbol, normalize_ticker, resolve_name
from recommendation.daily_service import DailyRecommendationService
from recommendation.run_context import latest_completed_run


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
        ("STO 기준 통과", diagnostics.get("sto_pass_comparisons", 0), "STO 최소 기준까지 통과한 종목-패턴 비교"),
        ("매칭 종목", diagnostics.get("symbols_with_matches", 0), "과거 급등직전 패턴과 하나 이상 매칭된 종목"),
        ("최종 추천", diagnostics.get("final_recommendations", 0), "주봉 유사도 순으로 저장된 종목"),
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
        f"주봉 {weekly:.0f}% 이상 · STO {sto:.0f}% 이상 · 순위는 주봉 유사도 단일 기준"
    )


def run(market_code: str = "kr") -> None:
    import streamlit as st

    profile = get_market_profile(market_code)
    st.set_page_config(page_title=f"ADE {profile.name} 추천 생성", page_icon="📅", layout="wide")
    st.markdown(
        f"""
        <style>
        :root{{--ink:#14263a;--muted:#6d8194;--line:rgba(77,125,168,.18)}}
        .stApp{{background:linear-gradient(135deg,#f7fbff,#eef5fb 52%,#f9fcff);color:var(--ink)}}
        .block-container{{max-width:1540px;padding-top:1.05rem;padding-bottom:3rem}}
        .hero{{padding:28px 32px;border-radius:24px;background:rgba(255,255,255,.91);border:1px solid var(--line);box-shadow:0 18px 48px rgba(42,88,130,.10);margin-bottom:18px}}
        .hero h1{{margin:5px 0 7px;font-size:34px;letter-spacing:-.04em}}.hero p{{margin:0;color:var(--muted)}}
        .eyebrow{{font-size:12px;letter-spacing:.15em;font-weight:850;color:#2f78ba}}
        div[data-testid="stMetric"]{{background:rgba(255,255,255,.82);border:1px solid var(--line);padding:15px 17px;border-radius:16px}}
        div[data-testid="stDataFrame"]{{border-radius:16px;overflow:hidden;border:1px solid var(--line)}}
        </style>
        <div class="hero">
          <div class="eyebrow">ADE {profile.code.upper()} PRE-SURGE RECOMMENDATION</div>
          <h1>{profile.name} 급등직전 120일 패턴 추천</h1>
          <p>통합 추천 워크벤치와 같은 추천 실행·같은 DB·같은 순위 규칙을 사용합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    service = DailyRecommendationService(profile.db_path)
    try:
        readiness = inspect_market_db(profile.db_path, profile.code)
        runs = service.latest_runs(50)
        completed_runs = [
            row for row in runs
            if row["status"] == "COMPLETED" and int(row.get("recommendation_count") or 0) > 0
        ]
        common_latest = latest_completed_run(service.conn, profile.code)
        latest_completed = next(
            (row for row in completed_runs if common_latest and row["run_id"] == common_latest["run_id"]),
            completed_runs[0] if completed_runs else None,
        )
        latest_auto = next((row for row in completed_runs if row["run_type"] == "AUTO"), None)
        latest_manual = next((row for row in completed_runs if row["run_type"] == "MANUAL"), None)
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
        st.caption(
            f"최근 완료 실행 {latest_completed['finished_at'] if latest_completed else '없음'} · "
            f"자동 {latest_auto['finished_at'] if latest_auto else '없음'} · 수동 {latest_manual['finished_at'] if latest_manual else '없음'}"
        )

        st.markdown("### 추천 기준")
        o1, o2, o3, o4, o5 = st.columns(5)
        candidate_years = o1.number_input("과거 패턴 기간(년)", 1, 10, 2, 1, key=f"{profile.code}_replay_years")
        pattern_pool = o2.number_input("비교할 과거 패턴 수", 10, 1000, 100, 10, key=f"{profile.code}_weekly_pool")
        min_chart = o3.number_input("최소 주봉 유사도", 0.0, 100.0, 85.0, 1.0, key=f"{profile.code}_weekly")
        min_sto = o4.number_input("STO 통과 기준", 0.0, 100.0, 85.0, 1.0, key=f"{profile.code}_sto")
        top_n = o5.number_input("저장할 추천종목 수", 1, 50, 20, 1, key=f"{profile.code}_top_n")
        st.info("추천 순위는 주봉 유사도만 사용하고 STO는 최소 기준 통과 여부만 확인합니다.")

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
                st.warning("중단 요청을 보냈습니다.")
                st.rerun()

        live = get_status(profile.code)
        state = str(live.get("state", "IDLE"))
        if state in {"STARTING", "RUNNING", "CANCELLING"}:
            st.progress(float(live.get("progress", 0.0) or 0.0), text=str(live.get("message", "분석 중...")))
            _render_selected_options(st, live.get("diagnostics") or {})
            _render_diagnostics(st, live.get("diagnostics") or {})
        elif state == "COMPLETED":
            st.success(f"추천 완료 및 저장 · {int(live.get('recommendation_count', 0))}개 · {float(live.get('elapsed_seconds', 0.0)):.1f}초")
        elif state == "CANCELLED":
            st.warning("추천 생성이 사용자 요청으로 중단되었습니다. 아래 상세 결과에는 완료 실행만 표시합니다.")
        elif state == "STALE":
            st.warning(str(live.get("message") or "이전 작업 상태를 복구했습니다."))
        elif state == "FAILED":
            st.error(str(live.get("error_message") or "추천 생성에 실패했습니다."))

        st.divider()
        st.markdown("### 완료된 추천 이력")
        if not completed_runs:
            st.info(f"{profile.name}에 추천 결과가 저장된 완료 실행 이력이 없습니다.")
            return
        run_df = pd.DataFrame([{key: value for key, value in row.items() if key not in {"diagnostics", "parameters"}} for row in completed_runs])
        st.dataframe(run_df, use_container_width=True, hide_index=True)

        labels = {
            row["run_id"]: f"{row['started_at']} · {row['run_type']} · {row['recommendation_count']}개"
            for row in completed_runs
        }
        selected_run_id = st.selectbox(
            "상세 추천 결과",
            options=list(labels),
            index=0,
            format_func=lambda run_id: labels[run_id],
            key=f"{profile.code}_detail_completed_run",
        )
        selected_run = next(row for row in completed_runs if row["run_id"] == selected_run_id)
        st.caption(f"통합 워크벤치 기준 실행 ID: {latest_completed['run_id']} · 현재 선택: {selected_run_id}")
        _render_selected_options(st, selected_run.get("diagnostics") or selected_run.get("parameters") or {})
        _render_diagnostics(st, selected_run.get("diagnostics") or {})
        details = pd.DataFrame(service.recommendations_for_run(selected_run_id))
        if not details.empty:
            name_map = build_name_map(service.conn, profile.code)
            details["종목코드"] = details["ticker"].map(lambda value: normalize_ticker(value, profile.code))
            details["종목명"] = details.apply(
                lambda row: resolve_name(row.get("ticker"), row.get("name"), name_map, profile.code), axis=1
            )
            details["종목"] = details.apply(
                lambda row: display_symbol(row.get("종목명"), row.get("종목코드"), profile.code), axis=1
            )
            rename = {"final_similarity": "순위점수(주봉)", "weekly_similarity": "주봉 유사도", "sto_similarity": "STO 유사도"}
            preferred = ["rank_no", "종목", "종목코드", "종목명", "주봉 유사도", "STO 유사도", "decision"]
            shown = details.rename(columns=rename)
            st.dataframe(shown[[column for column in preferred if column in shown.columns]], use_container_width=True, hide_index=True)
            st.page_link("pages/14_Recommendation_Workbench.py", label="동일 실행을 통합 추천 워크벤치에서 보기", icon="📊")
        report_path = selected_run.get("report_path")
        if report_path and Path(str(report_path)).exists():
            st.caption(f"HTML 보고서: {report_path}")
    finally:
        service.close()


if __name__ == "__main__":
    run("kr")
