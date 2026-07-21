from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from dashboard.system_status import inspect_market_db
from maintenance.recommendation_runner import cancel_job, get_status, start_job
from markets.profiles import get_market_profile
from markets.symbol_display import build_name_map, display_symbol, normalize_ticker, resolve_name
from recommendation.daily_service import DailyRecommendationService
from recommendation.run_context import latest_completed_run


def run(market_code: str = "kr") -> None:
    profile = get_market_profile(market_code)
    st.set_page_config(page_title=f"ADE {profile.name} 추천", page_icon="📅", layout="wide")
    _style()

    service = DailyRecommendationService(profile.db_path)
    try:
        readiness = inspect_market_db(profile.db_path, profile.code)
        runs = service.latest_runs(50)
        completed = [r for r in runs if r["status"] == "COMPLETED" and int(r.get("recommendation_count") or 0) > 0]
        common_latest = latest_completed_run(service.conn, profile.code)
        latest = next((r for r in completed if common_latest and r["run_id"] == common_latest["run_id"]), completed[0] if completed else None)
        runtime = get_status(profile.code)

        _hero(profile, latest)
        _top_metrics(readiness, latest, runtime, profile.code)
        if not readiness.ready:
            st.error("추천 실행 전 데이터 준비가 필요합니다: " + " / ".join(readiness.issues))

        left, right = st.columns([1.05, 1.65], gap="large")
        with left:
            _execution_panel(profile, readiness, runtime)
        with right:
            _latest_result_panel(service, profile, latest)

        _history_panel(service, profile, completed)
    finally:
        service.close()


def _hero(profile, latest) -> None:
    market_note = "국내 시장 추천 생성과 최신 결과를 한 화면에서 관리합니다."
    if profile.code == "us":
        market_note = "미국 시장 세션과 추천 실행 결과를 Ticker 중심으로 관리합니다."
    st.markdown(
        f'<div class="hero"><div><div class="eyebrow">ADE · {profile.code.upper()} RECOMMENDATION</div>'
        f'<h1>{profile.name} 추천</h1><p>{market_note}</p></div>'
        f'<div class="hero-side">최근 완료<br><b>{str(latest.get("finished_at"))[:16] if latest else "없음"}</b></div></div>',
        unsafe_allow_html=True,
    )


def _top_metrics(readiness, latest, runtime, market: str) -> None:
    cols = st.columns(4)
    cols[0].metric("데이터 상태", "READY" if readiness.ready else "확인 필요")
    cols[1].metric("활성 종목", f"{readiness.active_symbols:,}")
    cols[2].metric("최근 추천", f"{int(latest.get('recommendation_count') or 0)}개" if latest else "없음")
    if market == "us":
        cols[3].metric("미국 시장", _us_session())
    else:
        cols[3].metric("작업 상태", str(runtime.get("state", "IDLE")))


def _execution_panel(profile, readiness, runtime) -> None:
    st.markdown('<div class="section-title"><h2>오늘의 추천 생성</h2><span>기준 확인 후 실행</span></div>', unsafe_allow_html=True)
    with st.container(border=True):
        c1, c2 = st.columns(2)
        years = c1.number_input("과거 패턴 기간(년)", 1, 10, 2, 1, key=f"new_{profile.code}_years")
        pool = c2.number_input("비교할 과거 패턴 수", 10, 1000, 100, 10, key=f"new_{profile.code}_pool")
        c3, c4 = st.columns(2)
        weekly = c3.number_input("최소 주봉 유사도", 0.0, 100.0, 85.0, 1.0, key=f"new_{profile.code}_weekly")
        sto = c4.number_input("STO 통과 기준", 0.0, 100.0, 85.0, 1.0, key=f"new_{profile.code}_sto")
        top_n = st.slider("저장할 추천 종목 수", 5, 50, 20, 1, key=f"new_{profile.code}_top")
        st.info("추천 순위는 주봉 유사도만 사용하며 STO는 최소 기준 통과 여부만 확인합니다.")

        running = bool(runtime.get("running"))
        if st.button(f"{profile.name} 추천 생성 및 저장", type="primary", use_container_width=True, disabled=running or not readiness.ready):
            if start_job(
                profile.code, profile.db_path, top_n=int(top_n), weekly_pool_n=int(pool),
                candidate_years=int(years), use_recent_replay=True, use_weekly_filter=True,
                min_weekly_similarity=float(weekly), use_sto_filter=True, min_sto_similarity=float(sto),
            ):
                st.rerun()
        b1, b2 = st.columns([3, 1])
        if b1.button("진행상태 새로고침", use_container_width=True, key=f"new_{profile.code}_refresh"):
            st.rerun()
        if b2.button("중단", use_container_width=True, disabled=not running, key=f"new_{profile.code}_cancel"):
            if cancel_job(profile.code):
                st.rerun()

        live = get_status(profile.code)
        state = str(live.get("state", "IDLE"))
        if state in {"STARTING", "RUNNING", "CANCELLING"}:
            st.progress(float(live.get("progress", 0.0) or 0.0), text=str(live.get("message", "분석 중")))
        elif state == "COMPLETED":
            st.success(f"추천 완료 · {int(live.get('recommendation_count', 0))}개 · {float(live.get('elapsed_seconds', 0.0)):.1f}초")
        elif state == "FAILED":
            st.error(str(live.get("error_message") or "추천 생성 실패"))


def _latest_result_panel(service, profile, latest) -> None:
    st.markdown('<div class="section-title"><h2>최근 추천 결과</h2><span>가장 최근 완료 실행</span></div>', unsafe_allow_html=True)
    if not latest:
        st.info("완료된 추천 결과가 없습니다.")
        return
    details = pd.DataFrame(service.recommendations_for_run(latest["run_id"]))
    if details.empty:
        st.info("추천 결과가 비어 있습니다.")
        return

    name_map = build_name_map(service.conn, profile.code)
    details["종목코드"] = details["ticker"].map(lambda v: normalize_ticker(v, profile.code))
    details["종목명"] = details.apply(lambda r: resolve_name(r.get("ticker"), r.get("name"), name_map, profile.code), axis=1)
    details["종목"] = details.apply(lambda r: display_symbol(r.get("종목명"), r.get("종목코드"), profile.code), axis=1)
    details["주봉"] = details["weekly_similarity"].astype(float).round(1)
    details["STO"] = details["sto_similarity"].astype(float).round(1)

    k1, k2, k3 = st.columns(3)
    k1.metric("실행 시각", str(latest.get("finished_at") or "-")[:16])
    k2.metric("실행 유형", str(latest.get("run_type") or "-"))
    k3.metric("추천 결과", f"{len(details)}종목")

    if profile.code == "us":
        shown = details.rename(columns={"종목코드": "Ticker", "종목명": "Company", "rank_no": "Rank"})
        columns = [c for c in ["Rank", "Ticker", "Company", "주봉", "STO", "decision"] if c in shown.columns]
    else:
        shown = details.rename(columns={"rank_no": "순위"})
        columns = [c for c in ["순위", "종목", "주봉", "STO", "decision"] if c in shown.columns]
    st.dataframe(shown[columns], use_container_width=True, hide_index=True, height=510)
    st.page_link("pages/14_Recommendation_Workbench.py", label="투자 워크벤치에서 검토", icon="📊", use_container_width=True)


def _history_panel(service, profile, completed) -> None:
    with st.expander("이전 실행 이력", expanded=False):
        if not completed:
            st.info("완료된 실행 이력이 없습니다.")
            return
        rows = [{k: v for k, v in r.items() if k not in {"diagnostics", "parameters"}} for r in completed]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _us_session() -> str:
    now = datetime.now(ZoneInfo("America/New_York"))
    minutes = now.hour * 60 + now.minute
    if now.weekday() >= 5:
        return "휴장"
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return "장전"
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return "개장"
    if 16 * 60 <= minutes < 20 * 60:
        return "장후"
    return "마감"


def _style() -> None:
    st.markdown(
        """
        <style>
        :root{--ink:#14263a;--muted:#6d8194;--line:rgba(77,125,168,.18)}
        .stApp{background:linear-gradient(135deg,#f7fbff,#eef5fb 52%,#f9fcff);color:var(--ink)}
        .block-container{max-width:1700px;padding-top:.8rem;padding-bottom:3rem}
        .hero{display:flex;justify-content:space-between;align-items:flex-end;padding:25px 30px;border-radius:24px;background:rgba(255,255,255,.92);border:1px solid var(--line);box-shadow:0 18px 48px rgba(42,88,130,.10);margin-bottom:16px}
        .hero h1{margin:4px 0 6px;font-size:34px;letter-spacing:-.04em}.hero p{margin:0;color:var(--muted)}
        .eyebrow{font-size:12px;letter-spacing:.15em;font-weight:850;color:#2f78ba}.hero-side{text-align:right;color:var(--muted)}.hero-side b{color:var(--ink)}
        .section-title{display:flex;justify-content:space-between;align-items:end;margin:16px 0 8px}.section-title h2{margin:0;font-size:20px}.section-title span{font-size:13px;color:var(--muted)}
        div[data-testid="stMetric"]{background:rgba(255,255,255,.86);border:1px solid var(--line);padding:14px 16px;border-radius:16px}
        div[data-testid="stDataFrame"]{border-radius:16px;overflow:hidden;border:1px solid var(--line)}
        </style>
        """,
        unsafe_allow_html=True,
    )
