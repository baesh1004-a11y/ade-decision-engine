from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from markets.symbol_display import build_name_map, display_symbol, normalize_ticker, resolve_name
from recommendation.run_context import load_latest_context


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="ADE 종합 검증 리포트", page_icon="📋", layout="wide")
    st.title("종합 검증 리포트")
    st.caption("한국·미국 최신 완료 추천 실행의 검증 현황을 한 화면에서 비교합니다.")

    market = st.segmented_control(
        "시장",
        options=["all", "kr", "us"],
        default="all",
        format_func=lambda value: {"all": "전체", "kr": "🇰🇷 한국", "us": "🇺🇸 미국"}[value],
    )

    targets = []
    if market in {"all", "kr"}:
        targets.append(("kr", "한국", Path("datahub/market.db")))
    if market in {"all", "us"}:
        targets.append(("us", "미국", Path("datahub/us_market.db")))

    frames: list[pd.DataFrame] = []
    run_cards: list[dict[str, object]] = []
    for market_code, market_name, db_path in targets:
        frame, run_info = _load_market_report(db_path, market_code, market_name)
        if run_info:
            run_cards.append(run_info)
        if not frame.empty:
            frames.append(frame)

    if not frames:
        st.info("표시할 완료 추천 또는 검증 결과가 없습니다.")
        return

    report = pd.concat(frames, ignore_index=True)
    validated = int(report["검증여부"].eq("완료").sum())
    total = len(report)
    decisions = report[report["검증여부"].eq("완료")]["검증결과"].value_counts()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("전체 추천", f"{total}개")
    c2.metric("검증 완료", f"{validated}개")
    c3.metric("검증률", f"{(validated / total * 100) if total else 0:.1f}%")
    c4.metric("매수 검토", f"{int(decisions.get('매수 검토', 0))}개")
    c5.metric("관찰", f"{int(decisions.get('관찰', 0))}개")

    if run_cards:
        st.markdown("### 최신 실행 요약")
        for item in run_cards:
            st.caption(
                f"{item['시장']} · run_id {item['run_id']} · 완료 {item['완료시각']} · "
                f"추천 {item['추천수']}개 · 검증 {item['검증수']}개"
            )

    st.markdown("### 추천군 검증 결과")
    decision_filter = st.multiselect(
        "검증결과 필터",
        options=["매수 검토", "관찰", "보류", "제외", "미검증"],
        default=["매수 검토", "관찰", "보류", "제외", "미검증"],
    )
    filtered = report[report["검증결과"].isin(decision_filter)].copy()
    st.dataframe(filtered, width="stretch", hide_index=True, height=620)

    csv = filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "CSV 다운로드",
        data=csv,
        file_name="ade_validation_report.csv",
        mime="text/csv",
    )


def _load_market_report(db_path: Path, market_code: str, market_name: str) -> tuple[pd.DataFrame, dict[str, object] | None]:
    if not db_path.exists():
        return pd.DataFrame(), None

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        context = load_latest_context(conn, market_code, 100)
        if context is None:
            return pd.DataFrame(), None
        name_map = build_name_map(conn, market_code)
        rows = []
        for item in context.recommendations:
            ticker = normalize_ticker(item.get("ticker"), market_code)
            name = resolve_name(ticker, item.get("name"), name_map, market_code)
            validation = context.validations.get(ticker) or context.validations.get(str(item.get("ticker")))
            decision = _decision_label(str(validation.get("decision"))) if validation else "미검증"
            rows.append(
                {
                    "시장": market_name,
                    "순위": int(item.get("rank_no") or 0),
                    "종목": display_symbol(name, ticker, market_code),
                    "종목코드": ticker,
                    "주봉 유사도": float(item.get("weekly_similarity") or 0),
                    "STO 유사도": float(item.get("sto_similarity") or 0),
                    "검증여부": "완료" if validation else "미검증",
                    "검증결과": decision,
                    "시장점수": float(validation.get("market_score") or 0) if validation else None,
                    "업종점수": float(validation.get("sector_score") or 0) if validation else None,
                    "위험점수": float(validation.get("risk_score") or 0) if validation else None,
                    "run_id": context.run_id,
                }
            )
        return pd.DataFrame(rows), {
            "시장": market_name,
            "run_id": context.run_id,
            "완료시각": context.finished_at or "-",
            "추천수": len(context.recommendations),
            "검증수": len(context.validations),
        }
    finally:
        conn.close()


def _decision_label(value: str) -> str:
    return {
        "FINAL BUY": "매수 검토",
        "BUY WATCH": "관찰",
        "HOLD": "보류",
        "PASS": "제외",
    }.get(value, value or "미검증")
