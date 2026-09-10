"""ADE Decision Desk: explicit routes, saved evidence and a continuous review flow."""

from __future__ import annotations

import logging
import sqlite3
from html import escape
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from dashboard.desk_charts import compare_prices, compare_sto
from dashboard.desk_data import DeskData, decode, number
from dashboard.desk_review import load_review, save_review
from markets.profiles import get_market_profile

LOGGER = logging.getLogger(__name__)
PAGES = ("상황종합판", "추천결과", "주문", "JP Radar", "Replay Watch", "실행기록")
PAGE_LABELS = {
    "추천결과": "추천 · 근거 검증",
    "주문": "주문 · 보유 관리",
    "실행기록": "실행 기록",
}
STATUS_LABELS = {
    "CREATED": "준비",
    "VALIDATING": "확인 중",
    "RUNNING": "실행 중",
    "SUCCEEDED": "완료",
    "PARTIAL_SUCCESS": "일부 완료",
    "FAILED": "실패",
    "CANCELLED": "중단",
    "PENDING": "대기",
    "SKIPPED": "건너뜀",
    "COMPLETED": "완료",
}


def _fmt(value, suffix="", digits=1) -> str:
    parsed = number(value)
    return "—" if parsed is None else f"{parsed:,.{digits}f}{suffix}"


def _go(page: str) -> None:
    st.session_state.ade_primary_page = page
    st.session_state.ade_order_confirmation = False


def _market_changed() -> None:
    st.session_state.ade_market = st.session_state.desk_market
    st.session_state.ade_order_ticker = None
    st.session_state.ade_order_confirmation = False


def _sidebar() -> tuple[str, str]:
    st.session_state.setdefault("ade_primary_page", "추천결과")
    st.session_state.setdefault("ade_market", "kr")
    st.session_state.setdefault("ade_owner_id", uuid4().hex)
    if st.session_state.get("desk_navigation") != st.session_state.ade_primary_page:
        st.session_state.desk_navigation = st.session_state.ade_primary_page
    with st.sidebar:
        st.markdown(
            '<div class="desk-brand">ADE</div><div class="desk-brand-sub">DECISION DESK</div>',
            unsafe_allow_html=True,
        )
        st.radio(
            "작업 공간",
            PAGES,
            key="desk_navigation",
            format_func=lambda v: PAGE_LABELS.get(v, v),
            on_change=lambda: _go(st.session_state.desk_navigation),
        )
        st.divider()
        if st.session_state.get("desk_market") != st.session_state.ade_market:
            st.session_state.desk_market = st.session_state.ade_market
        market = st.selectbox(
            "분석 시장",
            ["kr", "us"],
            key="desk_market",
            format_func=lambda v: "한국 · KRW" if v == "kr" else "미국 · USD",
            on_change=_market_changed,
        )
        if market != st.session_state.ade_market:
            st.session_state.ade_market = market
            st.session_state.ade_order_ticker = None
            st.session_state.ade_order_confirmation = False
        _connection_control()
        st.markdown(
            '<div class="desk-side-note">패턴의 발견에서<br>근거를 확인한 판단까지</div>',
            unsafe_allow_html=True,
        )
    return str(market), str(st.session_state.ade_primary_page)


def _connection_control() -> None:
    from dashboard.kis_zero_base_bridge import (
        kis_configuration_status,
        probe_kis_connection,
    )

    with st.expander("증권사 연결"):
        config = kis_configuration_status()
        st.caption(
            "KIS · "
            + (
                "모의투자"
                if config.get("paper_enabled")
                else str(config.get("environment") or "미설정")
            )
        )
        if not config.get("configured"):
            st.caption("연결 설정이 필요합니다. 추천 검토는 계속 사용할 수 있습니다.")
        if st.button(
            "KIS 연결 확인",
            key="desk_kis_probe",
            disabled=not config.get("configured"),
            use_container_width=True,
        ):
            with st.spinner("계좌 연결을 확인하고 있습니다."):
                st.session_state.desk_kis_probe_result = probe_kis_connection(
                    get_market_profile("kr").db_path
                )
        result = st.session_state.get("desk_kis_probe_result")
        if result and result.get("rest_ok") and result.get("account_ok"):
            st.success("연결 정상")
            st.caption(f"확인 시각 {result.get('captured_at') or '미확인'}")
        elif result:
            st.error(str(result.get("error") or "연결을 확인하지 못했습니다."))
        elif config.get("configured"):
            st.caption("설정 완료 · 실제 연결 미확인")


def _generation(profile, health: dict) -> None:
    from maintenance.recommendation_runner import cancel_job, get_status, start_job

    runtime = get_status(profile.code)
    running = bool(runtime.get("running"))
    key = f"desk_run_{profile.code}"
    with st.expander("추천 계산 설정", expanded=False):
        columns = st.columns(5)
        years = columns[0].number_input("과거 기간 · 년", 1, 10, 2, key=key + "years")
        pool = columns[1].number_input(
            "과거 패턴 수", 10, 1000, 100, 10, key=key + "pool"
        )
        weekly = columns[2].number_input(
            "주봉 최소 유사도", 0.0, 100.0, 85.0, 1.0, key=key + "weekly"
        )
        sto = columns[3].number_input(
            "STO 최소 유사도", 0.0, 100.0, 85.0, 1.0, key=key + "sto"
        )
        top = columns[4].number_input("추천 수", 1, 50, 20, key=key + "top")
        st.caption("주봉 유사도로 순위를 정하고, STO는 통과 조건으로 사용합니다.")
    start, refresh, summary = st.columns([1.1, 1, 3.5])
    with start:
        if st.button(
            "추천 새로 계산",
            type="primary",
            disabled=running or not health.get("patterns"),
            use_container_width=True,
        ):
            request = start_job(
                profile.code,
                profile.db_path,
                top_n=int(top),
                weekly_pool_n=int(pool),
                candidate_years=int(years),
                use_recent_replay=True,
                use_weekly_filter=True,
                min_weekly_similarity=float(weekly),
                use_sto_filter=True,
                min_sto_similarity=float(sto),
            )
            if request:
                st.rerun()
            else:
                st.info("이 시장의 추천 계산이 이미 진행 중입니다.")
    with refresh:
        if st.button("상태 새로고침", use_container_width=True):
            st.rerun()
    with summary:
        latest = str(health.get("latest_date") or "미확인")
        st.caption(
            f"시세 기준 {latest} · 과거 패턴 {_fmt(health.get('patterns'), '개', 0)}"
        )
    if running:
        progress = min(
            1.0,
            max(
                0.0,
                float(runtime.get("overall_progress") or runtime.get("progress") or 0),
            ),
        )
        st.progress(progress, text=str(runtime.get("stage_label") or "추천 계산 중"))
        if st.button("계산 중단", key=key + "cancel"):
            cancel_job(profile.code)
            st.rerun()
    elif runtime.get("state") == "FAILED":
        st.warning(
            "최근 추천 계산이 완료되지 않았습니다. 이전 완료 결과를 검토할 수 있습니다."
        )
        with st.expander("실패 원인 확인"):
            st.text(str(runtime.get("error_message") or "실행 기록을 확인하세요."))


def _choose_run(data: DeskData, runs: list[dict]):
    key = "desk_selected_run_" + data.market
    ids = [str(row["run_id"]) for row in runs]
    if st.session_state.get(key) and st.session_state[key] not in ids:
        retained = data.run(st.session_state[key])
        if retained:
            runs = [*runs, retained]
            ids.append(str(retained["run_id"]))
    if st.session_state.get(key) not in ids:
        st.session_state[key] = ids[0]
    lookup = {str(row["run_id"]): row for row in runs}
    widget_key = "desk_run_selector_" + data.market
    st.session_state[widget_key] = st.session_state[key]
    with st.sidebar:
        st.divider()
        st.selectbox(
            "검토할 추천",
            ids,
            key=widget_key,
            index=ids.index(st.session_state[key]),
            on_change=lambda: st.session_state.update(
                {key: st.session_state[widget_key]}
            ),
            format_func=lambda value: f"{str(lookup[value].get('finished_at') or lookup[value].get('started_at') or '')[:16].replace('T', ' ')}"
            f" · {lookup[value].get('actual_recommendation_count', lookup[value].get('recommendation_count', 0))}종목",
        )
    if st.session_state[key] != ids[0]:
        notice, action = st.columns([4, 1])
        notice.info("이전 실행을 검토 중입니다. 선택한 추천과 비교 기준을 유지합니다.")
        action.button(
            "최신 결과 보기", on_click=lambda: st.session_state.update({key: ids[0]})
        )
    return data.context(st.session_state[key]), lookup[st.session_state[key]]


def _candidates(context, query: str):
    rows = [dict(row) for row in context.recommendations]
    for row in rows:
        row["symbol"] = (
            row.get("name")
            or decode(row.get("payload_json")).get("name")
            or str(row["ticker"])
        )
    term = query.strip().casefold()
    filtered = [
        row
        for row in rows
        if not term or term in f"{row['ticker']} {row['symbol']}".casefold()
    ]
    # Filtering only hides rows; their saved rank and score never change.
    key = f"desk_ticker_{context.market}_{context.run_id}"
    if filtered and st.session_state.get(key) not in [
        str(row["ticker"]) for row in filtered
    ]:
        st.session_state[key] = str(filtered[0]["ticker"])
    for row in filtered:
        ticker = str(row["ticker"])
        label = f"{int(row['rank_no']):02d}   {row['symbol']}"
        if st.button(
            label,
            key=f"desk_select_{context.market}_{context.run_id}_{ticker}",
            type="primary" if st.session_state.get(key) == ticker else "secondary",
            use_container_width=True,
        ):
            st.session_state[key] = ticker
            st.rerun()
        st.markdown(
            f'<div class="desk-candidate-note">{escape(ticker)} · 주봉 {_fmt(row.get("weekly_similarity"), "%")} · STO {_fmt(row.get("sto_similarity"), "%")}</div>',
            unsafe_allow_html=True,
        )
    if not filtered:
        st.info("검색 조건과 일치하는 추천 종목이 없습니다.")
    return next(
        (row for row in filtered if str(row["ticker"]) == st.session_state.get(key)),
        None,
    )


def _comparison(data: DeskData, context, selected: dict) -> None:
    payload = decode(selected.get("payload_json"))
    ticker = str(selected["ticker"])
    matches = [
        item for item in (payload.get("replay_matches") or []) if isinstance(item, dict)
    ]
    st.markdown(
        f'<div class="desk-section-label">02 / 원천 근거 비교</div><div class="desk-symbol">{escape(str(selected["symbol"]))}</div><div class="desk-symbol-code">{escape(ticker)} · 추천 순위 #{int(selected["rank_no"])}</div>',
        unsafe_allow_html=True,
    )
    stats = [
        ("주봉 유사도", _fmt(selected.get("weekly_similarity"), "%")),
        ("STO 유사도", _fmt(selected.get("sto_similarity"), "%")),
        ("저장된 유사 사례", f"{len(matches)}건"),
    ]
    st.markdown(
        '<div class="desk-score-row">'
        + "".join(
            f'<div class="desk-score"><span>{label}</span><strong>{value}</strong></div>'
            for label, value in stats
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    reasons = payload.get("reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    if reasons:
        st.markdown(
            '<div class="desk-reason">'
            + "<br>".join(escape(str(v)) for v in reasons[:3])
            + "</div>",
            unsafe_allow_html=True,
        )
    if not matches:
        st.info("이 추천에는 저장된 과거 사례가 없습니다.")
        return
    prefix = f"{context.market}_{context.run_id}_{ticker}"
    index = st.selectbox(
        "비교할 과거 사례",
        list(range(len(matches))),
        key="desk_match_" + prefix,
        format_func=lambda i: f"{i + 1}. {matches[i].get('name') or matches[i].get('ticker') or '과거 사례'} · {matches[i].get('event_date') or '날짜 미확인'}",
    )
    match = matches[index]
    evidence = data.evidence(
        selected, match, str(context.finished_at or context.started_at or "")
    )
    mode = st.radio(
        "비교 항목",
        ["가격 · 거래량", "STO 3계층", "사례 성과"],
        horizontal=True,
        key="desk_mode_" + prefix,
        label_visibility="collapsed",
    )
    if mode == "사례 성과":
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "사례": item.get("name") or item.get("ticker"),
                        "기준일": item.get("event_date"),
                        "주봉 유사도": number(item.get("weekly_similarity")),
                        "STO 유사도": number(item.get("sto_similarity")),
                        "이후 최대수익 (%)": number(item.get("max_return")),
                        "이후 최대낙폭 (%)": number(item.get("max_drawdown")),
                    }
                    for item in matches
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("저장된 과거 결과입니다. 비어 있는 수치는 확인되지 않은 값입니다.")
    elif len(evidence.current) >= 120 and len(evidence.historical) >= 120:
        figure = (
            compare_prices(evidence.current, evidence.historical)
            if mode == "가격 · 거래량"
            else compare_sto(evidence.current, evidence.historical)
        )
        st.plotly_chart(
            figure,
            use_container_width=True,
            key=f"desk_chart_{prefix}_{index}_{mode}",
            config={"displaylogo": False, "responsive": True, "scrollZoom": False},
        )
        st.caption(
            f"현재 기준일 {str(evidence.current.iloc[-1]['Date'])[:10]} · 과거 기준일 {str(evidence.historical.iloc[-1]['Date'])[:10]} · 가격 출처 {evidence.source}"
        )
    for warning in evidence.warnings:
        st.warning(warning)
    with st.expander("저장된 계산 근거 전체"):
        for reason in reasons:
            st.write(str(reason))
        st.caption(f"추천 실행 {context.run_id}")


def _review(context, selected: dict) -> None:
    market, ticker, run_id = context.market, str(selected["ticker"]), context.run_id
    owner = str(st.session_state.ade_owner_id)
    saved = load_review(owner, market, run_id, ticker)
    prefix = f"desk_review_{market}_{run_id}_{ticker}"
    st.markdown(
        '<div class="desk-section-label">03 / 판단 기록</div>', unsafe_allow_html=True
    )
    st.markdown("### 검토 메모")
    checks = {}
    for key, label in [
        ("price", "가격·거래량 비교"),
        ("sto", "STO 전환 흐름 확인"),
        ("environment", "시장·위험 요인 확인"),
    ]:
        checks[key] = st.checkbox(
            label, value=bool(saved.get("checks", {}).get(key)), key=prefix + key
        )
    options = ["검토 중", "관찰", "주문 검토"]
    verdict = st.radio(
        "내 판단",
        options,
        index=options.index(saved.get("verdict"))
        if saved.get("verdict") in options
        else 0,
        key=prefix + "verdict",
    )
    note = st.text_area(
        "판단 근거와 반대 근거",
        value=str(saved.get("note") or ""),
        height=140,
        placeholder="과거 사례와의 차이, 진입 조건, 확인할 위험 요인",
        key=prefix + "note",
    )
    review = {"checks": checks, "verdict": verdict, "note": note}
    if st.button("검토 내용 저장", key=prefix + "save", use_container_width=True):
        save_review(owner, market, run_id, ticker, selected, review)
        st.success("이 추천 실행에 검토 내용을 저장했습니다.")
    validation = context.validations.get(ticker)
    if st.button(
        "시장·업종 환경 확인", key=prefix + "validate", use_container_width=True
    ):
        from recommendation.validation_service import run_selected_validation

        try:
            with st.spinner("시장·업종 환경을 확인하고 있습니다."):
                result = run_selected_validation(
                    get_market_profile(market).db_path,
                    run_id,
                    selected,
                    decode(selected.get("payload_json")),
                )
                if result.status == "PARTIAL_SUCCESS":
                    st.session_state.desk_validation_notice = "환경 검토는 저장됐지만 이후 성과 관찰 등록이 완료되지 않았습니다. 실행 기록에서 원인을 확인하세요."
            st.rerun()
        except Exception as exc:
            LOGGER.exception(
                "Environment review failed: run=%s ticker=%s", run_id, ticker
            )
            st.error(f"환경 검토를 완료하지 못했습니다: {exc}")
    if validation:
        with st.expander("저장된 환경 검토"):
            st.json(validation)
    st.markdown('<div class="desk-rule"></div>', unsafe_allow_html=True)
    if st.button(
        "주문 후보로 보내기",
        key=prefix + "order",
        type="primary",
        use_container_width=True,
    ):
        from dashboard.order_candidate_store import upsert_candidate

        save_review(owner, market, run_id, ticker, selected, review)
        upsert_candidate(
            owner,
            market,
            ticker,
            str(selected["symbol"]),
            source_run_id=run_id,
            source_rank=int(selected["rank_no"]),
        )
        st.session_state.ade_order_ticker = ticker
        st.session_state.ade_order_symbol = str(selected["symbol"])
        # The broker ticket retains its existing explicit confirmation step.
        _go("주문")
        st.rerun()
    st.caption(
        "후보를 보내면 주문 화면으로 이동합니다. 주문 조건과 수량은 그곳에서 확인합니다."
    )


def _desk(profile) -> None:
    data = DeskData(profile.db_path, profile.code)
    health = data.health()
    notice = st.session_state.pop("desk_validation_notice", None)
    if notice:
        st.warning(notice)
    st.markdown(
        '<div class="desk-eyebrow">RESEARCH / DECISION</div>', unsafe_allow_html=True
    )
    st.title("추천과 근거를 한눈에")
    st.markdown(
        '<div class="desk-context"><span class="desk-chip">저장된 추천 기준</span><span>발견 · 비교 · 판단 · 주문 검토</span></div>',
        unsafe_allow_html=True,
    )
    _generation(profile, health)
    runs = data.runs()
    if not runs:
        st.markdown(
            '<div class="desk-empty"><h2>첫 추천 결과를 준비하세요</h2><p>시장 데이터와 과거 급등 패턴이 준비되면 추천 계산을 시작할 수 있습니다. 계산이 끝나면 종목별 근거와 비교 차트가 이곳에 표시됩니다.</p></div>',
            unsafe_allow_html=True,
        )
        a, b = st.columns(2)
        a.metric("가격 데이터 종목", _fmt(health.get("prices"), "", 0))
        b.metric("과거 급등 패턴", _fmt(health.get("patterns"), "", 0))
        return
    context, run = _choose_run(data, runs)
    if context is None:
        st.warning("선택한 실행 기록을 읽을 수 없습니다.")
        return
    scores = [number(row.get("weekly_similarity")) for row in context.recommendations]
    scores = [value for value in scores if value is not None]
    kpis = st.columns(4)
    for col, label, value in zip(
        kpis,
        ["추천 종목", "평균 주봉 유사도", "환경 검토 기록", "연결된 주문 대기"],
        [
            f"{context.recommendation_count}개",
            _fmt(sum(scores) / len(scores) if scores else None, "%"),
            f"{len(context.validations)}개",
            f"{len(context.current_orders)}건",
        ],
    ):
        col.metric(label, value)
    parameters = decode(run.get("parameters_json"))
    st.caption(
        f"완료 {str(context.finished_at or '')[:19].replace('T', ' ')} · 실행 조건 주봉 {_fmt(parameters.get('min_weekly_similarity'), '%')} / STO {_fmt(parameters.get('min_sto_similarity'), '%')}"
    )
    if not context.recommendations:
        st.info(
            "이 실행에서 조건을 통과한 종목은 0개입니다. 이전 결과는 왼쪽의 ‘검토할 추천’에서 선택할 수 있습니다."
        )
        return
    left, center, right = st.columns([1.05, 2.6, 1.15], gap="medium")
    with left, st.container(border=True):
        st.markdown(
            '<div class="desk-candidates"><div class="desk-section-label">01 / 추천 목록</div></div>',
            unsafe_allow_html=True,
        )
        query = st.text_input(
            "종목 찾기",
            placeholder="종목명 또는 코드",
            key="desk_search_" + profile.code,
        )
        selected = _candidates(context, query)
    if selected:
        with center, st.container(border=True):
            _comparison(data, context, selected)
        with right, st.container(border=True):
            _review(context, selected)


def _history(profile) -> None:
    data = DeskData(profile.db_path, profile.code)
    st.title("실행 기록")
    rows = data.ledger()
    if not rows:
        st.info("새로 실행한 추천과 종합 판단부터 단계별 기록이 쌓입니다.")
        return
    kinds = {
        "recommendation": "추천",
        "decision": "종합 판단",
        "validation": "환경 검토",
    }
    display = pd.DataFrame(
        [
            {
                "실행": row["run_id"],
                "종류": kinds.get(row["kind"], row["kind"]),
                "종목": row["ticker"],
                "상태": STATUS_LABELS.get(row["status"], row["status"]),
                "시작": row["created_at"],
                "완료": row["finished_at"],
            }
            for row in rows
        ]
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
    chosen = st.selectbox("단계별 기록 확인", [row["run_id"] for row in rows])
    stages = data.stages(chosen)
    labels = {
        "INPUT": "입력 확인",
        "DECISION": "종합 판단",
        "RESULT": "결과 저장",
        "ENVIRONMENT": "시장·업종 확인",
        "VALIDATION": "환경 검토 저장",
        "FEEDBACK": "관찰 등록",
        "RECOMMEND": "추천 계산",
        "REPORT": "보고서 생성",
        "PERSIST": "추천 결과 저장",
    }
    for stage in stages:
        st.markdown(
            f"**{labels.get(stage['name'], stage['name'])}** · {STATUS_LABELS.get(stage['status'], stage['status'])}"
        )
        if stage.get("error"):
            st.error(stage["error"])
    st.download_button(
        "실행 목록 내려받기",
        display.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"ade_runs_{profile.code}.csv",
        mime="text/csv",
    )


def _legacy(page: str) -> None:
    # Lazy imports avoid market lookups and broker construction on the research route.
    from dashboard import ade_ui_v1_app as base
    from dashboard import ade_ui_v1_entrypoint as terminal

    base._init_state()
    if page != "주문":
        base._release_live_lease()
    if page == "주문":
        st.title("주문 · 보유 관리")
        if st.session_state.ade_market == "us":
            from dashboard.desk_orders import render_us_orders

            render_us_orders()
            return
        # A retained legacy market widget must not override the sidebar selection.
        st.session_state.ade_order_market = st.session_state.ade_market
        terminal._render_orders()
    elif page == "JP Radar":
        st.title("JP Radar")
        base._render_jp_radar()
    elif page == "Replay Watch":
        from dashboard.replay_target_workspace import render_replay_watch_workspace

        st.title("Replay Watch")
        render_replay_watch_workspace()
    else:
        from dashboard.overview_workspace_no_charts import render_overview_workspace

        st.title("상황종합판")
        render_overview_workspace(base)


def run() -> None:
    st.set_page_config(
        page_title="ADE · Decision Desk",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        "<style>"
        + Path(__file__).with_suffix(".css").read_text(encoding="utf-8")
        + "</style>",
        unsafe_allow_html=True,
    )
    market, page = _sidebar()
    profile = get_market_profile(market)
    if page != "주문" and st.session_state.get("ade_live_subscription_ticker"):
        from dashboard.ade_ui_v1_app import _release_live_lease

        _release_live_lease()
    try:
        if page == "추천결과":
            _desk(profile)
        elif page == "실행기록":
            _history(profile)
        else:
            _legacy(page)
    except (sqlite3.Error, OSError, ValueError) as exc:
        LOGGER.exception("Decision desk failed: page=%s market=%s", page, market)
        st.error(
            "데이터를 불러오지 못했습니다. 기존 결과를 보존한 상태로 조회를 중단했습니다."
        )
        with st.expander("오류 자세히"):
            st.text(str(exc))
    st.markdown(
        '<div class="desk-footer">ADE Decision Desk · 유사도, 과거 사례 성과, 내 판단을 각각 확인하세요.</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    run()
