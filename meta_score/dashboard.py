from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

from feedback.engine import FeedbackEngine
from meta_score.engine import MetaScoreEngine
from prediction.replay_prediction import HorizonPrediction, ReplayPrediction
from recommendation.event_recommender import EventRecommendation, ReplayMatch


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    market_name = "미국" if "us_market" in db_path else "한국"
    market_code = "us" if market_name == "미국" else "kr"
    st.set_page_config(page_title=f"ADE {market_name} 추천 검증", page_icon="✅", layout="wide")
    _style(st)

    st.markdown(
        f"""
        <div class="hero">
          <div>
            <div class="eyebrow">ADE · 추천 검증 단계</div>
            <h1>{market_name} 추천 검증</h1>
            <p>통합 추천 워크벤치와 동일한 최신 완료 추천 실행을 시장·업종·위험 체크리스트로 검증합니다.</p>
          </div>
          <div class="formula">동일 run_id 검증 · 과거 실행 혼합 금지</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    latest_run = _latest_completed_run(db_path, market_code)
    if latest_run is None:
        st.info("완료된 추천 실행 중 저장된 추천종목이 없습니다. 먼저 추천 생성을 완료하세요.")
        return

    run_id = str(latest_run["run_id"])
    st.caption(
        f"통합 워크벤치 연결 실행 ID: {run_id} · 완료 시각: {latest_run.get('finished_at') or '-'} · "
        f"추천 수: {latest_run.get('recommendation_count') or 0}개"
    )

    c1, c2 = st.columns([1, 2])
    top_n = c1.number_input("검증할 추천종목 수", min_value=3, max_value=50, value=20, step=1)
    load_button = c2.button("이 추천 실행 검증", type="primary", use_container_width=True)

    state_key = f"meta_score_results:{db_path}"
    source_key = f"meta_score_source_run:{db_path}"
    inserted_key = f"meta_feedback_inserted:{db_path}"

    # 새 추천 실행이 완료되면 기존 Streamlit 세션 캐시를 자동 폐기한다.
    cached_run = st.session_state.get(source_key)
    should_reload = load_button or cached_run != run_id or state_key not in st.session_state

    if should_reload:
        with st.spinner("최신 추천 실행의 시장·업종·위험 상태를 확인하고 있습니다..."):
            recommendations = _load_recommendations_for_run(db_path, run_id, int(top_n))
            if recommendations:
                results = MetaScoreEngine().score(recommendations)
                _save_final_decisions(db_path, run_id, results)
                st.session_state[state_key] = results
                st.session_state[source_key] = run_id
                feedback = FeedbackEngine(db_path)
                try:
                    inserted = feedback.register_meta_results(results)
                finally:
                    feedback.close()
                st.session_state[inserted_key] = inserted
            else:
                st.session_state[state_key] = []
                st.session_state[source_key] = run_id
                st.session_state[inserted_key] = 0

    results = st.session_state.get(state_key, [])
    st.caption(f"연결 흐름: 추천 실행 {run_id} → 추천 검증 → 주문관리")

    if not results:
        st.warning("선택된 완료 실행에 유효한 추천 payload가 없습니다. 추천 실행 결과를 다시 확인하세요.")
        return

    final_buy = sum(1 for item in results if item.decision == "FINAL BUY")
    buy_watch = sum(1 for item in results if item.decision == "BUY WATCH")
    hold = sum(1 for item in results if item.decision == "HOLD")
    best = results[0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("매수 검토", final_buy)
    k2.metric("관찰", buy_watch)
    k3.metric("보류", hold)
    k4.metric("추천 1위", best.name or best.ticker, f"주봉 {best.breakdown.replay:.2f}%")

    ranking = pd.DataFrame([
        {
            "순위": item.rank,
            "종목코드": item.ticker,
            "종목명": item.name,
            "검증결과": _decision_label(item.decision),
            "주봉 순위점수": item.breakdown.replay,
            "시장상태": item.market_signal,
            "업종상태": item.sector_signal,
            "위험상태": "PASS" if item.breakdown.risk >= 60 else "주의",
        }
        for item in results
    ])
    st.markdown("### 추천 검증 결과")
    st.dataframe(ranking, use_container_width=True, hide_index=True)

    selected = st.selectbox(
        "상세 종목",
        list(range(len(results))),
        format_func=lambda i: f"#{results[i].rank} {results[i].name or results[i].ticker} · 주봉 {results[i].breakdown.replay:.2f}%",
    )
    item = results[selected]
    st.markdown(
        f"""
        <div class="decision-card">
          <div><div class="eyebrow">추천 검증 #{item.rank}</div><h2>{item.name or item.ticker}</h2>
          <p>{item.market_code.upper()}:{item.ticker} · 시장 {item.market_signal} · 업종 {item.sector_signal}</p></div>
          <div class="score">{item.breakdown.replay:.2f}%<small>주봉 순위점수 · {_decision_label(item.decision)}</small></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### 검증 근거")
    for reason in item.reasons:
        st.markdown(f"- {reason}")
    st.caption("검증 결과는 반드시 현재 연결된 동일 run_id로 주문관리에 전달됩니다.")
    st.page_link("pages/9_Trading_Desk.py" if market_code == "kr" else "pages/12_US_Trading_Desk.py", label="주문관리 열기", icon="🛒", use_container_width=True)


def _decision_label(value: str) -> str:
    return {
        "FINAL BUY": "매수 검토",
        "BUY WATCH": "관찰",
        "HOLD": "보류",
        "PASS": "제외",
    }.get(value, value)


def _latest_completed_run(db_path: str, market_code: str) -> dict[str, object] | None:
    path = Path(db_path)
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT r.run_id, r.started_at, r.finished_at, r.run_type, r.recommendation_count
            FROM recommendation_runs r
            WHERE r.status='COMPLETED'
              AND EXISTS(
                SELECT 1 FROM daily_recommendations d
                WHERE d.run_id=r.run_id AND d.market=?
              )
            ORDER BY r.started_at DESC
            LIMIT 1
            """,
            (market_code,),
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def _save_final_decisions(db_path: str, source_run_id: str, results: list[object]) -> None:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS final_decisions (
                source_run_id TEXT NOT NULL, rank_no INTEGER NOT NULL,
                market TEXT NOT NULL, ticker TEXT NOT NULL, name TEXT,
                decision TEXT NOT NULL, grade TEXT NOT NULL,
                meta_score REAL NOT NULL, pattern_score REAL NOT NULL,
                radar_score REAL NOT NULL, market_score REAL NOT NULL,
                sector_score REAL NOT NULL, risk_score REAL NOT NULL,
                target_return REAL, stop_return REAL, payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_run_id, rank_no)
            )
            """
        )
        conn.execute("DELETE FROM final_decisions WHERE source_run_id=?", (source_run_id,))
        for item in results:
            conn.execute(
                """
                INSERT INTO final_decisions(
                    source_run_id, rank_no, market, ticker, name, decision, grade,
                    meta_score, pattern_score, radar_score, market_score,
                    sector_score, risk_score, target_return, stop_return, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_run_id, item.rank, item.market_code, item.ticker, item.name,
                    item.decision, item.grade, item.breakdown.replay, item.breakdown.replay,
                    item.breakdown.jp_radar, item.breakdown.market, item.breakdown.sector,
                    item.breakdown.risk, item.target_return, item.stop_return,
                    json.dumps(item.to_dict(), ensure_ascii=False),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _load_recommendations_for_run(db_path: str, run_id: str, limit: int) -> list[EventRecommendation]:
    path = Path(db_path)
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT payload_json FROM daily_recommendations WHERE run_id=? ORDER BY rank_no LIMIT ?",
            (run_id, limit),
        ).fetchall()
        recommendations: list[EventRecommendation] = []
        for row in rows:
            try:
                recommendations.append(_recommendation_from_payload(json.loads(str(row["payload_json"]))))
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return recommendations
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _recommendation_from_payload(payload: dict[str, object]) -> EventRecommendation:
    replay_matches = [ReplayMatch(**item) for item in payload.get("replay_matches", [])]
    prediction_payload = payload.get("prediction")
    prediction = None
    if isinstance(prediction_payload, dict):
        horizons = tuple(HorizonPrediction(**item) for item in prediction_payload.get("horizons", []))
        prediction = ReplayPrediction(
            sample_count=int(prediction_payload["sample_count"]), horizons=horizons,
            seven_day_up_probability=float(prediction_payload["seven_day_up_probability"]),
            seven_day_expected_return=float(prediction_payload["seven_day_expected_return"]),
            seven_day_median_return=float(prediction_payload["seven_day_median_return"]),
            expected_max_return_7d=float(prediction_payload["expected_max_return_7d"]),
            expected_max_return_20d=float(prediction_payload["expected_max_return_20d"]),
            expected_peak_day=float(prediction_payload["expected_peak_day"]),
            expected_mdd_7d=float(prediction_payload["expected_mdd_7d"]),
            target_return=float(prediction_payload["target_return"]),
            stop_return=float(prediction_payload["stop_return"]),
            holding_days=int(prediction_payload["holding_days"]), grade=str(prediction_payload["grade"]),
        )
    return EventRecommendation(
        market=str(payload["market"]), ticker=str(payload["ticker"]), name=payload.get("name"),
        recent_event_date=str(payload["recent_event_date"]), recent_money_ratio=float(payload["recent_money_ratio"]),
        matched_event_id=str(payload["matched_event_id"]), matched_event_date=str(payload["matched_event_date"]),
        weekly_similarity=float(payload["weekly_similarity"]), sto_similarity=float(payload["sto_similarity"]),
        final_similarity=float(payload["final_similarity"]), matched_max_return=payload.get("matched_max_return"),
        matched_max_drawdown=payload.get("matched_max_drawdown"), decision=str(payload["decision"]),
        reasons=[str(item) for item in payload.get("reasons", [])], replay_matches=replay_matches, prediction=prediction,
    )


def _style(st: object) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#f9fbff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1600px;padding-top:1.3rem}
        .hero,.decision-card{display:flex;justify-content:space-between;align-items:center;padding:24px 28px;border:1px solid rgba(76,145,207,.23);border-radius:26px;background:rgba(255,255,255,.82);box-shadow:0 18px 50px rgba(63,105,145,.12);margin-bottom:16px}
        .hero h1,.decision-card h2{margin:3px 0;letter-spacing:-.04em}.hero p,.decision-card p{margin:5px 0;color:#647b92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        .formula{padding:12px 16px;border-radius:999px;background:#eaf4ff;color:#286ba6;font-weight:800}.score{font-size:42px;font-weight:900;color:#0e6fc4;text-align:right}.score small{display:block;font-size:14px;color:#5f758b}
        @media(max-width:768px){.block-container{padding:.75rem}.hero,.decision-card{display:block;padding:18px}.score{text-align:left;margin-top:12px;font-size:36px}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE 추천 검증")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
