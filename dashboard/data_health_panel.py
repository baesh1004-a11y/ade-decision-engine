from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def _status_label(ok: bool, waiting: bool = False) -> str:
    if waiting:
        return "대기"
    return "정상" if ok else "오류"


def build_data_health_rows(
    *,
    current: pd.DataFrame,
    current_source: str,
    current_warning: str | None,
    historical: pd.DataFrame,
    pattern: Any,
    replay_count: int,
    news_count: int,
    disclosure_count: int,
    validation: Any,
    market: str,
) -> list[dict[str, str]]:
    current_ok = current is not None and not current.empty
    historical_ok = historical is not None and not historical.empty and pattern is not None
    sto_ready = current_ok and historical_ok
    rows = [
        {
            "영역": "가격",
            "데이터": "일봉 OHLCV",
            "상태": _status_label(current_ok),
            "세부": f"{len(current)}행 · {current_source}" if current_ok else (current_warning or current_source or "데이터 없음"),
        },
        {
            "영역": "패턴",
            "데이터": "Replay 사례",
            "상태": _status_label(replay_count > 0),
            "세부": f"{replay_count}건" if replay_count > 0 else "저장 사례 없음",
        },
        {
            "영역": "패턴",
            "데이터": "과거 패턴 봉",
            "상태": _status_label(historical_ok),
            "세부": f"{len(historical)}행" if historical_ok else "선택 패턴 또는 봉 데이터 없음",
        },
        {
            "영역": "기술분석",
            "데이터": "STO 비교 입력",
            "상태": _status_label(sto_ready),
            "세부": "현재/과거 데이터 준비됨" if sto_ready else "현재·과거 데이터 중 일부 누락",
        },
        {
            "영역": "콘텐츠",
            "데이터": "뉴스",
            "상태": _status_label(news_count > 0),
            "세부": f"{news_count}건" if news_count > 0 else "조회 결과 없음",
        },
        {
            "영역": "콘텐츠",
            "데이터": "공시",
            "상태": _status_label(disclosure_count > 0, waiting=market != "kr"),
            "세부": f"{disclosure_count}건" if disclosure_count > 0 else ("국내 종목만 확인" if market != "kr" else "없음 또는 DART 미설정"),
        },
        {
            "영역": "검증",
            "데이터": "시장·업종 환경",
            "상태": _status_label(validation is not None),
            "세부": "검증 결과 있음" if validation is not None else "아직 계산되지 않음",
        },
        {
            "영역": "수급",
            "데이터": "외국인·기관",
            "상태": "미연결",
            "세부": "데이터 공급 경로 미구축",
        },
        {
            "영역": "수급",
            "데이터": "프로그램·공매도",
            "상태": "미연결",
            "세부": "데이터 공급 경로 미구축",
        },
    ]
    return rows


def render_data_health_panel(rows: list[dict[str, str]]) -> None:
    st.markdown("### 데이터 연결 상태")
    frame = pd.DataFrame(rows)
    normal = int((frame["상태"] == "정상").sum())
    errors = int((frame["상태"] == "오류").sum())
    missing = int((frame["상태"] == "미연결").sum())
    waiting = int((frame["상태"] == "대기").sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("정상", f"{normal}개")
    c2.metric("오류", f"{errors}개")
    c3.metric("미연결", f"{missing}개")
    c4.metric("대기", f"{waiting}개")
    st.dataframe(frame, hide_index=True, use_container_width=True)
    st.caption("이 표는 현재 선택 종목 기준의 런타임 점검 결과입니다. 정상 수신 여부와 미연결 항목을 구분해 표시합니다.")
