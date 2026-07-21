from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from dashboard.system_status import inspect_market_db
from maintenance.recommendation_runner import cancel_job, get_status, start_job
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, display_symbol, normalize_ticker, resolve_name
from recommendation.daily_service import DailyRecommendationService


_DEFAULT_SETTINGS = {
    "candidate_years": 2,
    "weekly_pool_n": 100,
    "min_weekly_similarity": 85.0,
    "min_sto_similarity": 85.0,
    "top_n": 20,
}


def _settings_path(market_code: str) -> Path:
    return Path("output") / f"{market_code}_recommendation_ui_settings.json"


def _parameters(values: dict[str, object] | None) -> dict[str, object]:
    values = values or {}
    return {
        "candidate_years": int(values.get("candidate_years", values.get("replay_years", _DEFAULT_SETTINGS["candidate_years"])) or _DEFAULT_SETTINGS["candidate_years"]),
        "weekly_pool_n": int(values.get("weekly_pool_n", values.get("pattern_pool", _DEFAULT_SETTINGS["weekly_pool_n"])) or _DEFAULT_SETTINGS["weekly_pool_n"]),
        "min_weekly_similarity": float(values.get("min_weekly_similarity", _DEFAULT_SETTINGS["min_weekly_similarity"]) or 0),
        "min_sto_similarity": float(values.get("min_sto_similarity", _DEFAULT_SETTINGS["min_sto_similarity"]) or 0),
        "top_n": int(values.get("top_n", values.get("recommendation_count", _DEFAULT_SETTINGS["top_n"])) or _DEFAULT_SETTINGS["top_n"]),
    }


def _load_saved_settings(market_code: str, fallback: dict[str, object] | None = None) -> dict[str, object]:
    path = _settings_path(market_code)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _parameters(payload)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return _parameters(fallback or _DEFAULT_SETTINGS)


def _save_settings(market_code: str, values: dict[str, object]) -> None:
    path = _settings_path(market_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**_parameters(values), "updated_at": datetime.now().isoformat(timespec="seconds")}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _initialize_widget_state(st, market_code: str, fallback: dict[str, object] | None) -> None:
    saved = _load_saved_settings(market_code, fallback)
    mapping = {
        f"{market_code}_replay_years": saved["candidate_years"],
        f"{market_code}_weekly_pool": saved["weekly_pool_n"],
        f"{market_code}_weekly": saved["min_weekly_similarity"],
        f"{market_code}_sto": saved["min_sto_similarity"],
        f"{market_code}_top_n": saved["top_n"],
    }
    for key, value in mapping.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _persist_widget_state(st, market_code: str) -> None:
    _save_settings(
        market_code,
        {
            "candidate_years": st.session_state.get(f"{market_code}_replay_years", _DEFAULT_SETTINGS["candidate_years"]),
            "weekly_pool_n": st.session_state.get(f"{market_code}_weekly_pool", _DEFAULT_SETTINGS["weekly_pool_n"]),
            "min_weekly_similarity": st.session_state.get(f"{market_code}_weekly", _DEFAULT_SETTINGS["min_weekly_similarity"]),
            "min_sto_similarity": st.session_state.get(f"{market_code}_sto", _DEFAULT_SETTINGS["min_sto_similarity"]),
            "top_n": st.session_state.get(f"{market_code}_top_n", _DEFAULT_SETTINGS["top_n"]),
        },
    )


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


def _render_applied_settings(st, values: dict[str, object] | None, title: str = "실행 적용 기준") -> None:
    p = _parameters(values)
    st.markdown(f"#### {title}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("과거 패턴 기간", f"{p['candidate_years']}년")
    c2.metric("비교 패턴 수", f"{p['weekly_pool_n']:,}개")
    c3.metric("최소 주봉", f"{p['min_weekly_similarity']:.1f}%")
    c4.metric("STO 기준", f"{p['min_sto_similarity']:.1f}%")
    c5.metric("저장 목표", f"{p['top_n']}개")


def _format_elapsed(seconds: object) -> str:
    total = max(0, int(float(seconds or 0)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}시간 {minutes}분 {secs}초"
    if minutes:
        return f"{minutes}분 {secs}초"
    return f"{secs}초"


def _heartbeat_text(age: object) -> str:
    if age is None:
        return "확인 불가"
    seconds = max(0, int(float(age)))
    return "방금" if seconds < 2 else f"{seconds}초 전"


def _health_text(value: object, unknown: str = "확인 불가") -> str:
    if value is True:
        return "정상"
    if value is False:
        return "끊김"
    return unknown


def _render_live_status(st, live: dict[str, object], run_parameters: dict[str, object] | None) -> None:
    state = str(live.get("state") or "IDLE")
    running = bool(live.get("running"))
    stage = str(live.get("stage_label") or live.get("stage") or "-")
    current = int(live.get("current") or live.get("processed_symbols") or 0)
    total = int(live.get("total") or live.get("total_symbols") or 0)
    remaining = live.get("remaining_symbols")
    ticker = live.get("current_ticker") or live.get("ticker") or "-"
    matched = int(live.get("matched_symbols") or (live.get("diagnostics") or {}).get("symbols_with_matches", 0) or 0)
    overall = float(live.get("overall_progress", live.get("progress", 0.0)) or 0.0)
    stage_progress = float(live.get("stage_progress", live.get("progress", 0.0)) or 0.0)

    if state in {"STARTING", "RUNNING", "CANCELLING"} and running:
        st.success("실제 작업 생존 신호를 확인했습니다. 추천 작업이 실행 중입니다.")
    elif state in {"STARTING", "RUNNING", "CANCELLING"}:
        st.error("상태값은 실행 중이지만 작업 생존 신호를 확인하지 못했습니다.")

    _render_applied_settings(st, run_parameters or live.get("diagnostics") or {}, "현재 실행에 실제 적용된 기준")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("실행 판정", "정상 실행 중" if running else state)
    c2.metric("현재 단계", stage)
    c3.metric("전체 진행률", f"{overall * 100:.1f}%")
    c4.metric("경과 시간", _format_elapsed(live.get("elapsed_seconds")))

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("처리 종목", f"{current:,} / {total:,}" if total else f"{current:,}")
    d2.metric("최근 처리 종목", str(ticker))
    d3.metric("추천 기준 통과", f"{matched:,}종목")
    d4.metric("남은 종목", f"{int(remaining):,}" if remaining is not None else "-")

    h1, h2, h3 = st.columns(3)
    h1.metric("최근 생존 신호", _heartbeat_text(live.get("heartbeat_age_seconds")))
    h2.metric("작업 스레드", _health_text(live.get("thread_alive"), "외부 프로세스"))
    h3.metric("작업 잠금 파일", _health_text(live.get("lock_exists")))

    st.progress(overall, text=str(live.get("message") or "분석 중..."))
    st.caption(f"단계 진행률 {stage_progress * 100:.1f}% · 마지막 상태 갱신 {live.get('updated_at') or '-'}")


def _history_frame(runs: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for run in runs:
        p = _parameters(run.get("parameters") or {})
        rows.append({
            "실행 시작": run.get("started_at"),
            "완료 시각": run.get("finished_at") or "-",
            "유형": run.get("run_type"),
            "상태": run.get("status"),
            "기간(년)": p["candidate_years"],
            "패턴 수": p["weekly_pool_n"],
            "주봉 기준": p["min_weekly_similarity"],
            "STO 기준": p["min_sto_similarity"],
            "저장 목표": p["top_n"],
            "추천 결과": int(run.get("recommendation_count") or 0),
            "소요(초)": round(float(run.get("elapsed_seconds") or 0), 1),
            "오류": run.get("error_message") or "",
            "run_id": run.get("run_id"),
        })
    return pd.DataFrame(rows)


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
          <p>투자 워크벤치와 같은 추천 실행·같은 DB·같은 순위 규칙을 사용합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    service = DailyRecommendationService(profile.db_path)
    try:
        readiness = inspect_market_db(profile.db_path, profile.code)
        runs = service.latest_runs(50)
        completed_runs = [row for row in runs if row.get("status") == "COMPLETED"]
        latest_completed = completed_runs[0] if completed_runs else None
        latest_auto = next((row for row in completed_runs if row.get("run_type") == "AUTO"), None)
        latest_manual = next((row for row in completed_runs if row.get("run_type") == "MANUAL"), None)
        active_run = next((row for row in runs if row.get("status") == "RUNNING"), None)
        runtime = get_status(profile.code)

        _initialize_widget_state(st, profile.code, (latest_completed or {}).get("parameters") or {})

        a, b, c, d = st.columns(4)
        a.metric("운영 준비", "READY" if readiness.ready else "NOT READY")
        b.metric("활성 종목", f"{readiness.active_symbols:,}")
        c.metric("최근 완료 추천", f"{int(latest_completed.get('recommendation_count') or 0):,}개" if latest_completed else "없음")
        d.metric("실행 상태", "RUNNING" if runtime.get("running") else str(runtime.get("state", "IDLE")))
        if not readiness.ready:
            st.error("추천 실행 전 데이터 준비가 필요합니다: " + " / ".join(readiness.issues))

        st.markdown("### 오늘의 추천 생성")
        o1, o2, o3, o4, o5 = st.columns(5)
        callback_args = (st, profile.code)
        candidate_years = o1.number_input("과거 패턴 기간(년)", 1, 10, step=1, key=f"{profile.code}_replay_years", on_change=_persist_widget_state, args=callback_args)
        pattern_pool = o2.number_input("비교할 과거 패턴 수", 10, 1000, step=10, key=f"{profile.code}_weekly_pool", on_change=_persist_widget_state, args=callback_args)
        min_chart = o3.number_input("최소 주봉 유사도", 0.0, 100.0, step=1.0, key=f"{profile.code}_weekly", on_change=_persist_widget_state, args=callback_args)
        min_sto = o4.number_input("STO 통과 기준", 0.0, 100.0, step=1.0, key=f"{profile.code}_sto", on_change=_persist_widget_state, args=callback_args)
        top_n = o5.number_input("저장할 추천종목 수", 1, 50, step=1, key=f"{profile.code}_top_n", on_change=_persist_widget_state, args=callback_args)
        st.info("추천 순위는 주봉 유사도만 사용하고 STO는 최소 기준 통과 여부만 확인합니다.")
        st.caption(
            f"다음 실행 예정 기준 · 최근 {int(candidate_years)}년 · 과거 패턴 {int(pattern_pool):,}개 · "
            f"주봉 {float(min_chart):.1f}% · STO {float(min_sto):.1f}% · 저장 목표 {int(top_n)}개"
        )

        running = bool(runtime.get("running"))
        start_col, refresh_col, stop_col = st.columns([4, 1.4, 1])
        if start_col.button(f"{profile.name} 추천종목 생성 및 저장", type="primary", use_container_width=True, key=f"{profile.code}_run", disabled=not readiness.ready or running):
            _persist_widget_state(st, profile.code)
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
            st.markdown("### 현재 실행 상세")
            _render_live_status(st, live, (active_run or {}).get("parameters") or {})
        elif state == "COMPLETED":
            st.success(f"추천 완료 및 저장 · {int(live.get('recommendation_count', 0))}개 · {_format_elapsed(live.get('elapsed_seconds'))}")
        elif state == "CANCELLED":
            st.warning("추천 생성이 사용자 요청으로 중단되었습니다. 실행 기록은 아래 이력에 남습니다.")
        elif state == "STALE":
            st.error(str(live.get("message") or "이전 작업 상태를 복구했습니다."))
            if live.get("error_message"):
                st.caption(str(live.get("error_message")))
        elif state == "FAILED":
            st.error(str(live.get("error_message") or "추천 생성에 실패했습니다."))

        st.divider()
        st.markdown("### 최근 완료된 추천 결과")
        if running:
            st.info("아래 결과는 현재 실행 결과가 아니라 이전에 완료된 실행 결과입니다. 현재 실행 결과는 완료 후 반영됩니다.")
        if not latest_completed:
            st.info(f"{profile.name}에 완료된 추천 실행이 없습니다.")
        else:
            st.caption(
                f"완료 시각 {latest_completed.get('finished_at') or '-'} · 실행 유형 {latest_completed.get('run_type') or '-'} · "
                f"추천 {int(latest_completed.get('recommendation_count') or 0)}종목"
            )
            _render_applied_settings(st, latest_completed.get("parameters") or {}, "이 결과에 실제 적용된 기준")
            selected_run_id = str(latest_completed["run_id"])
            details = pd.DataFrame(service.recommendations_for_run(selected_run_id))
            if details.empty:
                st.warning("이 실행은 정상 완료됐지만 추천 기준을 통과한 종목이 0개입니다.")
            else:
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
                st.page_link("pages/14_Recommendation_Workbench.py", label="투자 워크벤치에서 검토", icon="📊")

        with st.expander("이전 실행 이력", expanded=False):
            if not runs:
                st.info("저장된 실행 이력이 없습니다.")
            else:
                st.caption("추천 결과가 0개이거나 실패·중단된 실행도 모두 표시합니다.")
                st.dataframe(_history_frame(runs), use_container_width=True, hide_index=True)
                labels = {
                    str(row["run_id"]): (
                        f"{row.get('started_at')} · {row.get('status')} · "
                        f"{int(row.get('recommendation_count') or 0)}개"
                    )
                    for row in runs
                }
                history_run_id = st.selectbox(
                    "이력 상세 보기",
                    options=list(labels),
                    index=0,
                    format_func=lambda run_id: labels[run_id],
                    key=f"{profile.code}_detail_run",
                )
                history_run = next(row for row in runs if str(row["run_id"]) == history_run_id)
                _render_applied_settings(st, history_run.get("parameters") or {}, "선택 실행에 적용된 기준")
                if history_run.get("error_message"):
                    st.error(str(history_run.get("error_message")))
                _render_diagnostics(st, history_run.get("diagnostics") or {})
                report_path = history_run.get("report_path")
                if report_path and Path(str(report_path)).exists():
                    st.caption(f"HTML 보고서: {report_path}")

        st.caption(
            f"최근 자동 완료 {latest_auto['finished_at'] if latest_auto else '없음'} · "
            f"최근 수동 완료 {latest_manual['finished_at'] if latest_manual else '없음'} · "
            f"화면 확인 시각 {datetime.now().isoformat(timespec='seconds')}"
        )
    finally:
        service.close()


if __name__ == "__main__":
    run("kr")