from __future__ import annotations

from datetime import date
from html import escape

import pandas as pd

from replay_target.integrated import IntegratedWatchConfig, ReplayTargetIntegratedService


SESSION_RESULT_KEY = "ade_replay_watch_result"
SESSION_ERROR_KEY = "ade_replay_watch_error"


def _run_check(st, cfg: IntegratedWatchConfig) -> None:
    try:
        with st.spinner("KODEX/AK 일봉을 불러와 Target과 Path를 계산하는 중입니다..."):
            st.session_state[SESSION_RESULT_KEY] = ReplayTargetIntegratedService().run_live(cfg)
        st.session_state[SESSION_ERROR_KEY] = None
    except Exception as exc:
        st.session_state.pop(SESSION_RESULT_KEY, None)
        st.session_state[SESSION_ERROR_KEY] = str(exc)


def _diagnostic_html(messages: tuple[str, ...] | list[str]) -> str:
    rows = "".join(f"<div>• {escape(str(message))}</div>" for message in messages if str(message).strip())
    if not rows:
        return ""
    return (
        '<div class="ade-replay-diagnostic"><div class="title">점검 메모</div>'
        f'<div class="body">{rows}</div></div>'
    )


def render_replay_target_terminal() -> None:
    """Render Replay Target / Path Watch inside the ADE primary terminal."""

    import streamlit as st

    st.markdown(
        """
        <style>
        .ade-replay-shell{background:linear-gradient(180deg,#dff5f3 0%,#eef8ef 48%,#f4f6f8 100%);padding:16px;border-radius:30px}
        .ade-replay-hero{background:#fff;border-radius:28px;padding:24px;margin:8px 0 14px;box-shadow:0 4px 14px rgba(22,47,66,.04)}
        .ade-replay-title{font-size:30px;font-weight:950;letter-spacing:-.045em;color:#0b0f14}
        .ade-replay-sub{font-size:12px;color:#7b8794;margin-top:6px;line-height:1.5}
        .ade-replay-section{background:#fff;border-radius:26px;padding:20px 22px;margin:12px 0;border:1px solid rgba(15,23,42,.06);box-shadow:0 4px 14px rgba(22,47,66,.035)}
        .ade-replay-section-title{font-size:21px;font-weight:950;letter-spacing:-.03em;color:#111827;margin-bottom:4px}
        .ade-replay-section-sub{font-size:11px;color:#8a94a1;margin-bottom:14px}
        .ade-replay-diagnostic{background:#fff8db;border:1px solid #efd982;border-radius:18px;padding:14px 16px;margin:12px 0;color:#5f4b00}
        .ade-replay-diagnostic .title{font-size:12px;font-weight:900;margin-bottom:6px}
        .ade-replay-diagnostic .body{font-size:11px;line-height:1.6}
        .ade-replay-ready{background:#edf9f1;border:1px solid #c7e9d0;border-radius:16px;padding:11px 14px;margin:12px 0;color:#21623a;font-size:12px;font-weight:800}
        @media(max-width:900px){.ade-replay-title{font-size:25px}.ade-replay-section{padding:17px 18px}}
        </style>
        <div class="ade-replay-shell">
          <div class="ade-replay-hero">
            <div class="ade-replay-title">Replay Target / Path Watch</div>
            <div class="ade-replay-sub">KODEX 코스닥150(229200)의 2026-08-25 이후 경로를 AK홀딩스(006840·당시 애경유화)의 2011년 동그라미→A→B 경로와 비교합니다. 추천·주문 상태는 변경하지 않습니다.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cfg = IntegratedWatchConfig()

    top_left, top_right = st.columns([4, 1])
    with top_left:
        st.caption(
            "기본 기준 · 현재 T0 2026-08-25 · AK 대응점 2011-10-17~11-11 자동 탐색 · "
            "B 후보 2011-11-14~12-02 구간 저점 자동 선택 · 종가 기준"
        )
    with top_right:
        refresh = st.button("지금 점검", type="primary", use_container_width=True, key="ade_replay_watch_refresh")

    with st.expander("비교 기준 설정", expanded=False):
        c1, c2, c3 = st.columns(3)
        current_anchor = c1.date_input("현재 T0", value=date(2026, 8, 25), key="ade_replay_current_anchor")
        reference_start = c2.date_input("AK 대응점 시작", value=date(2011, 10, 17), key="ade_replay_reference_start")
        reference_end = c3.date_input("AK 대응점 종료", value=date(2011, 11, 11), key="ade_replay_reference_end")

        auto_anchor = st.checkbox("AK 대응 T0 자동 보정", value=True, key="ade_replay_auto_anchor")
        manual_anchor = ""
        if not auto_anchor:
            manual_anchor = st.text_input(
                "AK 대응 T0 직접 지정",
                value="",
                placeholder="YYYY-MM-DD",
                key="ade_replay_manual_anchor",
            )

        auto_target = st.checkbox("B Target 자동 보정", value=True, key="ade_replay_auto_target")
        if auto_target:
            t1, t2 = st.columns(2)
            target_start = t1.date_input("B 후보 시작", value=date(2011, 11, 14), key="ade_replay_target_start")
            target_end = t2.date_input("B 후보 종료", value=date(2011, 12, 2), key="ade_replay_target_end")
            target_date_value = None
        else:
            target_date = st.date_input("B Target 직접 지정", value=date(2011, 11, 25), key="ade_replay_target_date")
            target_start = date(2011, 11, 14)
            target_end = date(2011, 12, 2)
            target_date_value = target_date.isoformat()

        if st.button("설정 적용 후 점검", use_container_width=True, key="ade_replay_apply"):
            cfg = IntegratedWatchConfig(
                current_anchor_date=current_anchor.isoformat(),
                reference_window_start=reference_start.isoformat(),
                reference_window_end=reference_end.isoformat(),
                reference_anchor_date=None if auto_anchor else (manual_anchor.strip() or None),
                reference_target_date=target_date_value,
                reference_target_window_start=target_start.isoformat(),
                reference_target_window_end=target_end.isoformat(),
            )
            _run_check(st, cfg)

    if refresh:
        _run_check(st, cfg)

    if SESSION_RESULT_KEY not in st.session_state and not st.session_state.get(SESSION_ERROR_KEY):
        _run_check(st, cfg)

    error = st.session_state.get(SESSION_ERROR_KEY)
    if error:
        st.error(f"Replay Watch 점검 실패: {error}")
        st.caption("실데이터 수집 연결을 확인한 뒤 다시 점검하세요.")
        return

    result = st.session_state.get(SESSION_RESULT_KEY)
    if result is None:
        st.info("Replay Watch 결과가 아직 없습니다.")
        return

    target = getattr(result, "target", None)
    path = getattr(result, "path", None)
    current_close = getattr(result, "current_close", None)
    if current_close is None and target is not None:
        current_close = target.current_close

    st.markdown(
        '<div class="ade-replay-section"><div class="ade-replay-section-title">현재 판정</div>'
        '<div class="ade-replay-section-sub">Target 접근도와 T0 이후 경로 동조 상태</div>',
        unsafe_allow_html=True,
    )
    a, b, c, d, e, f = st.columns(6)
    a.metric("현재 종가", "-" if current_close is None else f"{current_close:,.0f}")
    b.metric("Target Score", "-" if target is None or target.target_score is None else f"{target.target_score:.1f}")
    c.metric("Target State", "-" if target is None else target.state)
    d.metric("Path Score", "-" if path is None or path.path_score is None else f"{path.path_score:.1f}")
    e.metric("Path State", "-" if path is None else path.path_state)
    f.metric("선행/지연", "-" if path is None else path.timing_label)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="ade-replay-section"><div class="ade-replay-section-title">기준 정렬</div>'
        '<div class="ade-replay-section-sub">현재 T0 · AK 대응 T0 · B Target · 데이터 범위</div>',
        unsafe_allow_html=True,
    )
    x1, x2, x3, x4 = st.columns(4)
    x1.metric("현재 T0", getattr(result, "resolved_current_anchor_date", None) or "-")
    x2.metric("AK 대응 T0", getattr(result, "resolved_reference_anchor_date", None) or "-")
    anchor_similarity = getattr(result, "anchor_similarity", None)
    x3.metric("Anchor 유사도", "-" if anchor_similarity is None else f"{anchor_similarity:.1f}")
    x4.metric("B Target", getattr(result, "resolved_reference_target_date", None) or "-")

    current_oldest = getattr(result, "current_oldest_date", None) or "?"
    reference_oldest = getattr(result, "reference_oldest_date", None) or "?"
    st.caption(
        f"현재 {result.current_source} · {result.current_rows}행 · 품질 {result.current_quality_score}/100 · "
        f"{current_oldest}~{result.current_latest_date or '-'} | "
        f"AK {result.reference_source} · {result.reference_rows}행 · 품질 {result.reference_quality_score}/100 · "
        f"{reference_oldest}~{result.reference_latest_date or '-'} · "
        f"Target 선택 {getattr(result, 'target_selection', '-')}"
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if target is not None:
        st.markdown(
            '<div class="ade-replay-section"><div class="ade-replay-section-title">STO 3계층</div>'
            '<div class="ade-replay-section-sub">주봉 STO 5·3·3 / 10·6·6 / 20·12·12</div>',
            unsafe_allow_html=True,
        )
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("단기 STO", "-" if target.short_sto is None else f"{target.short_sto:.1f}")
        s2.metric("중기 STO", "-" if target.middle_sto is None else f"{target.middle_sto:.1f}")
        s3.metric("장기 STO", "-" if target.long_sto is None else f"{target.long_sto:.1f}")
        s4.metric("배열", target.arrangement or "-")
        st.caption(target.note)
        st.markdown("</div>", unsafe_allow_html=True)

    if path is not None:
        st.markdown(
            '<div class="ade-replay-section"><div class="ade-replay-section-title">경로 증거</div>'
            '<div class="ade-replay-section-sub">언제부터 같거나 달라졌는지 거래일별 추적</div>',
            unsafe_allow_html=True,
        )
        p1, p2, p3, p4, p5 = st.columns(5)
        p1.metric("가격 방향", "-" if path.price_direction_match is None else ("일치" if path.price_direction_match else "불일치"))
        p2.metric("STO 방향", "-" if path.sto_direction_matches is None else f"{path.sto_direction_matches}/3")
        p3.metric("마지막 동조일", path.last_sync_date or "-")
        p4.metric("이탈 시작일", path.divergence_started_at or "-")
        p5.metric("이탈 확정일", path.break_confirmed_at or "-")
        if path.daily_matches:
            evidence = pd.DataFrame([item.to_dict() for item in path.daily_matches[-10:]]).rename(
                columns={
                    "current_date": "현재일",
                    "reference_date": "AK 대응일",
                    "score": "Path Score",
                    "price_direction_match": "가격방향",
                    "price_return_score": "수익률",
                    "sto_structure_score": "STO 구조",
                    "arrangement_match": "배열",
                    "current_return_1d": "현재 1D%",
                    "reference_return_1d": "AK 1D%",
                }
            )
            st.dataframe(evidence, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    if getattr(result, "ready", False):
        st.markdown('<div class="ade-replay-ready">Target과 Path 동시 판정 가능 · 현재 결과를 거래일별로 이어서 비교합니다.</div>', unsafe_allow_html=True)

    diagnostic = _diagnostic_html(getattr(result, "warnings", ()))
    if diagnostic:
        st.markdown(diagnostic, unsafe_allow_html=True)
