from __future__ import annotations

from datetime import date

import pandas as pd

from dashboard.design_system import apply_global_style, page_hero, section_header
from replay_target.integrated import IntegratedWatchConfig, ReplayTargetIntegratedService


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Replay Target / Path Watch", page_icon="🧭", layout="wide")
    apply_global_style(st)
    page_hero(
        st,
        "Replay Target / Path Watch",
        "KODEX 코스닥150이 2011년 AK홀딩스(당시 애경유화) 기준 경로와 얼마나 닮았고, 이후 경로를 계속 따라가는지 별도로 검증합니다.",
        eyebrow="ADE · RESEARCH VERIFICATION WORKBENCH",
        badge="종가 기반 · 주문 기능과 분리",
    )

    st.info(
        "이 화면은 추천·주문 엔진과 분리된 연구 기능입니다. Target 날짜 2011-12-14는 현재 차트에서 확인된 고점 날짜를 초기 기준으로 둔 값이며, STO 박스의 정확한 Target 날짜가 확정되면 바꿔야 합니다."
    )

    with st.form("replay-target-settings"):
        c1, c2, c3 = st.columns(3)
        current_anchor = c1.date_input("현재 T0", value=date(2026, 8, 25))
        reference_start = c2.date_input("과거 탐색 시작", value=date(2011, 9, 1))
        reference_end = c3.date_input("과거 탐색 종료", value=date(2011, 12, 31))

        c4, c5 = st.columns(2)
        auto_anchor = c4.checkbox("AK 기준일 자동 보정", value=True, help="현재 T0의 STO 3계층 구조와 가장 유사한 2011년 거래일을 탐색합니다.")
        manual_anchor = c4.text_input("AK 기준일 직접 지정 (YYYY-MM-DD)", value="", disabled=auto_anchor)
        target_date = c5.date_input("과거 Target 기준일", value=date(2011, 12, 14))
        submitted = st.form_submit_button("지금 점검", type="primary", use_container_width=True)

    if submitted:
        cfg = IntegratedWatchConfig(
            current_anchor_date=current_anchor.isoformat(),
            reference_window_start=reference_start.isoformat(),
            reference_window_end=reference_end.isoformat(),
            reference_anchor_date=None if auto_anchor else (manual_anchor.strip() or None),
            reference_target_date=target_date.isoformat(),
        )
        with st.spinner("KODEX/AK 일봉을 불러와 Target과 Path를 계산하는 중입니다..."):
            try:
                st.session_state["replay_target_result"] = ReplayTargetIntegratedService().run_live(cfg)
            except Exception as exc:
                st.session_state.pop("replay_target_result", None)
                st.error(f"점검 실패: {exc}")

    result = st.session_state.get("replay_target_result")
    if result is None:
        st.caption("설정을 확인한 뒤 ‘지금 점검’을 누르면 실제 일봉 데이터를 읽어 계산합니다.")
        return

    section_header(st, "판정 요약", "Target 접근도와 T0 이후 경로 동조 상태를 동시에 확인")
    target = result.target
    path = result.path
    a, b, c, d, e, f = st.columns(6)
    a.metric("현재 종가", "-" if target is None or target.current_close is None else f"{target.current_close:,.0f}")
    b.metric("Target Score", "-" if target is None or target.target_score is None else f"{target.target_score:.1f}")
    c.metric("Target State", "-" if target is None else target.state)
    d.metric("Path Score", "-" if path is None or path.path_score is None else f"{path.path_score:.1f}")
    e.metric("Path State", "-" if path is None else path.path_state)
    f.metric("선행/지연", "-" if path is None else path.timing_label)

    if result.ready:
        st.success("Target과 Path 동시 판정이 가능한 상태입니다.")
    else:
        st.warning("일부 기준일 또는 데이터가 부족해 완전한 동시 판정은 아직 불가능합니다.")

    section_header(st, "기준 정렬", "자동 보정 결과와 데이터 신뢰도")
    x1, x2, x3, x4 = st.columns(4)
    x1.metric("현재 T0", result.resolved_current_anchor_date or "-")
    x2.metric("AK 대응 T0", result.resolved_reference_anchor_date or "-")
    x3.metric("Anchor 유사도", "-" if result.anchor_similarity is None else f"{result.anchor_similarity:.1f}")
    x4.metric("Target 기준일", result.resolved_reference_target_date or "-")
    st.caption(
        f"현재 {result.current_source} · {result.current_rows}행 · 품질 {result.current_quality_score}/100 · 최신 {result.current_latest_date or '-'} | "
        f"과거 {result.reference_source} · {result.reference_rows}행 · 품질 {result.reference_quality_score}/100 · 최신 {result.reference_latest_date or '-'}"
    )

    if target is not None:
        section_header(st, "STO 3계층", "주봉 5·3·3 / 10·6·6 / 20·12·12")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("단기 STO", "-" if target.short_sto is None else f"{target.short_sto:.1f}")
        s2.metric("중기 STO", "-" if target.middle_sto is None else f"{target.middle_sto:.1f}")
        s3.metric("장기 STO", "-" if target.long_sto is None else f"{target.long_sto:.1f}")
        s4.metric("배열", target.arrangement or "-")
        st.caption(target.note)

    if path is not None:
        section_header(st, "경로 증거", "어느 거래일부터 같거나 달라졌는지 추적")
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("가격 방향", "-" if path.price_direction_match is None else ("일치" if path.price_direction_match else "불일치"))
        p2.metric("STO 방향", "-" if path.sto_direction_matches is None else f"{path.sto_direction_matches}/3")
        p3.metric("마지막 동조일", path.last_sync_date or "-")
        p4.metric("이탈 확정일", path.break_confirmed_at or "-")
        if path.divergence_started_at:
            st.warning(f"이탈 조짐 시작일: {path.divergence_started_at}")
        if path.daily_matches:
            rows = [item.to_dict() for item in path.daily_matches[-10:]]
            evidence = pd.DataFrame(rows).rename(
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

    if result.warnings:
        section_header(st, "점검 메모", "데이터와 기준일 관련 주의사항")
        for warning in result.warnings:
            st.warning(warning)


if __name__ == "__main__":
    main()
