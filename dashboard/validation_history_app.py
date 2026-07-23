from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    market_code = "us" if "us_market" in db_path else "kr"
    market_name = "미국" if market_code == "us" else "한국"
    st.set_page_config(page_title=f"ADE {market_name} 검증 이력", page_icon="🧾", layout="wide")
    st.title(f"{market_name} 검증 이력")
    st.caption("추천 실행별 검증 건수와 판단 분포를 시간순으로 확인합니다.")

    path = Path(db_path)
    if not path.exists():
        st.error(f"데이터베이스가 없습니다: {path}")
        return

    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        history = _load_history(conn, market_code)
        if history.empty:
            st.info("표시할 추천 또는 검증 이력이 없습니다.")
            return

        total_runs = len(history)
        validated_runs = int(history["검증수"].gt(0).sum())
        total_recommendations = int(history["추천수"].sum())
        total_validations = int(history["검증수"].sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("완료 실행", f"{total_runs}회")
        c2.metric("검증 실행", f"{validated_runs}회")
        c3.metric("누적 추천", f"{total_recommendations}개")
        c4.metric("누적 검증", f"{total_validations}개")

        st.markdown("### 실행별 검증 현황")
        st.dataframe(history, width="stretch", hide_index=True, height=620)

        selected_run = st.selectbox(
            "상세 실행 선택",
            history["run_id"].tolist(),
            format_func=lambda run_id: _run_label(history, run_id),
        )
        details = _load_details(conn, selected_run, market_code)
        if details.empty:
            st.info("선택한 실행에는 검증 결과가 없습니다.")
        else:
            st.markdown("### 선택 실행 상세")
            st.dataframe(details, width="stretch", hide_index=True, height=480)
    finally:
        conn.close()


def _load_history(conn: sqlite3.Connection, market: str) -> pd.DataFrame:
    tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "recommendation_runs" not in tables or "daily_recommendations" not in tables:
        return pd.DataFrame()

    has_decisions = "final_decisions" in tables
    decision_join = "LEFT JOIN final_decisions f ON f.source_run_id=r.run_id" if has_decisions else ""
    decision_columns = (
        "COUNT(DISTINCT f.ticker) AS validation_count, "
        "SUM(CASE WHEN f.decision='FINAL BUY' THEN 1 ELSE 0 END) AS final_buy, "
        "SUM(CASE WHEN f.decision='BUY WATCH' THEN 1 ELSE 0 END) AS buy_watch, "
        "SUM(CASE WHEN f.decision='HOLD' THEN 1 ELSE 0 END) AS hold_count, "
        "SUM(CASE WHEN f.decision='PASS' THEN 1 ELSE 0 END) AS pass_count"
        if has_decisions
        else "0 AS validation_count, 0 AS final_buy, 0 AS buy_watch, 0 AS hold_count, 0 AS pass_count"
    )
    rows = conn.execute(
        f"""
        SELECT r.run_id, r.started_at, r.finished_at, r.run_type, r.status,
               COUNT(DISTINCT d.ticker) AS recommendation_count,
               {decision_columns}
        FROM recommendation_runs r
        JOIN daily_recommendations d ON d.run_id=r.run_id AND d.market=?
        {decision_join}
        WHERE r.status='COMPLETED'
        GROUP BY r.run_id, r.started_at, r.finished_at, r.run_type, r.status
        ORDER BY r.started_at DESC
        LIMIT 100
        """,
        (market,),
    ).fetchall()
    return pd.DataFrame(
        [
            {
                "완료시각": row["finished_at"] or row["started_at"] or "-",
                "실행유형": row["run_type"] or "-",
                "추천수": int(row["recommendation_count"] or 0),
                "검증수": int(row["validation_count"] or 0),
                "검증률": round((int(row["validation_count"] or 0) / int(row["recommendation_count"] or 1)) * 100, 1),
                "매수 검토": int(row["final_buy"] or 0),
                "관찰": int(row["buy_watch"] or 0),
                "보류": int(row["hold_count"] or 0),
                "제외": int(row["pass_count"] or 0),
                "run_id": str(row["run_id"]),
            }
            for row in rows
        ]
    )


def _load_details(conn: sqlite3.Connection, run_id: str, market: str) -> pd.DataFrame:
    tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "final_decisions" not in tables:
        return pd.DataFrame()
    rows = conn.execute(
        """
        SELECT d.rank_no, d.ticker, d.name, d.weekly_similarity, d.sto_similarity,
               f.decision, f.market_score, f.sector_score, f.risk_score
        FROM daily_recommendations d
        JOIN final_decisions f ON f.source_run_id=d.run_id AND f.ticker=d.ticker
        WHERE d.run_id=? AND d.market=?
        ORDER BY d.rank_no
        """,
        (run_id, market),
    ).fetchall()
    return pd.DataFrame(
        [
            {
                "순위": int(row["rank_no"] or 0),
                "종목코드": str(row["ticker"]),
                "종목명": row["name"] or "-",
                "주봉 유사도": float(row["weekly_similarity"] or 0),
                "STO 유사도": float(row["sto_similarity"] or 0),
                "검증결과": _decision_label(str(row["decision"] or "")),
                "시장점수": float(row["market_score"] or 0),
                "업종점수": float(row["sector_score"] or 0),
                "위험점수": float(row["risk_score"] or 0),
            }
            for row in rows
        ]
    )


def _run_label(history: pd.DataFrame, run_id: str) -> str:
    row = history.loc[history["run_id"] == run_id].iloc[0]
    return f"{row['완료시각']} · 추천 {row['추천수']} · 검증 {row['검증수']} · {run_id}"


def _decision_label(value: str) -> str:
    return {
        "FINAL BUY": "매수 검토",
        "BUY WATCH": "관찰",
        "HOLD": "보류",
        "PASS": "제외",
    }.get(value, value or "미검증")
