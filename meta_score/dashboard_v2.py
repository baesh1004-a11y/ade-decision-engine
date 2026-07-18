from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

from feedback.engine import FeedbackEngine
from markets.symbol_display import build_name_map, display_symbol, normalize_ticker, resolve_name
from meta_score.dashboard import _recommendation_from_payload, _save_final_decisions
from meta_score.engine import MetaScoreEngine
from recommendation.run_context import load_latest_context


def run(db_path: str = "datahub/market.db") -> None:
    import streamlit as st

    market_code = "us" if "us_market" in db_path else "kr"
    market_name = "미국" if market_code == "us" else "한국"
    st.set_page_config(page_title=f"ADE {market_name} 추천 검증", page_icon="✅", layout="wide")
    _style(st)

    st.markdown(
        f"""
        <div class="hero">
          <div><div class="eyebrow">ADE · 추천 검증 단계</div><h1>{market_name} 추천 검증</h1>
          <p>현재 최신 완료 추천 실행을 읽기만 하며, 사용자가 검증 버튼을 눌렀을 때만 검증 결과를 저장합니다.</p></div>
          <div class="formula">동일 run_id · 수동 검증</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    path = Path(db_path)
    if not path.exists():
        st.error(f"데이터베이스가 없습니다: {path}")
        return

    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        context = load_latest_context(conn, market_code, 50)
        if context is None or not context.recommendations:
            st.info("추천 결과가 저장된 완료 실행이 없습니다. 먼저 추천 생성을 완료하세요.")
            return

        name_map = build_name_map(conn, market_code)
        recommendations = []
        for row in context.recommendations:
            item = dict(row)
            code = normalize_ticker(item.get("ticker"), market_code)
            name = resolve_name(code, item.get("name"), name_map, market_code)
            item["ticker"] = code
            item["name"] = name
            item["symbol"] = display_symbol(name, code, market_code)
            recommendations.append(item)

        st.caption(
            f"연결 run_id: {context.run_id} · 완료 시각: {context.finished_at or '-'} · "
            f"추천 {len(recommendations)}개 · 기존 검증 {len(context.validations)}개"
        )

        validate = st.button(
            f"현재 추천 전체 {len(recommendations)}개 검증",
            type="primary",
            use_container_width=True,
        )
        if validate:
            with st.spinner("시장·업종·위험 상태를 확인하고 있습니다..."):
                source_items = []
                for row in recommendations:
                    try:
                        payload = json.loads(str(row.get("payload_json") or "{}"))
                        payload["ticker"] = row["ticker"]
                        payload["name"] = row["name"]
                        source_items.append(_recommendation_from_payload(payload))
                    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                        continue
                results = MetaScoreEngine().score(source_items)
                _save_final_decisions(db_path, context.run_id, results)
                feedback = FeedbackEngine(db_path)
                try:
                    feedback.register_meta_results(results)
                finally:
                    feedback.close()
            st.success(f"동일 run_id에 검증 결과 {len(results)}개를 저장했습니다.")
            st.rerun()

        validations = context.validations
        if not validations:
            st.info("아직 검증하지 않았습니다. 위 버튼을 누르면 현재 추천 전체를 검증합니다.")
            return

        rows = []
        for item in recommendations:
            validation = validations.get(item["ticker"]) or validations.get(str(item.get("ticker")))
            if not validation:
                continue
            rows.append({
                "순위": int(item["rank_no"]),
                "종목": item["symbol"],
                "종목코드": item["ticker"],
                "종목명": item["name"],
                "검증결과": _decision_label(str(validation.get("decision"))),
                "주봉 순위점수": float(item.get("weekly_similarity") or 0),
                "STO 유사도": float(item.get("sto_similarity") or 0),
                "시장점수": float(validation.get("market_score") or 0),
                "업종점수": float(validation.get("sector_score") or 0),
                "위험점수": float(validation.get("risk_score") or 0),
            })

        st.markdown("### 추천 검증 결과")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        selected_from_workbench = normalize_ticker(st.session_state.get(f"workbench_selected_{market_code}") or "", market_code)
        default_index = next((i for i, row in enumerate(recommendations) if row["ticker"] == selected_from_workbench), 0)
        selected_index = st.selectbox(
            "상세 종목",
            list(range(len(recommendations))),
            index=default_index,
            format_func=lambda i: f"#{recommendations[i]['rank_no']} {recommendations[i]['symbol']}",
        )
        selected = recommendations[int(selected_index)]
        st.session_state[f"workbench_selected_{market_code}"] = selected["ticker"]
        validation = validations.get(selected["ticker"])
        if validation:
            st.markdown(
                f"""
                <div class="decision-card"><div><div class="eyebrow">추천 검증 #{selected['rank_no']}</div>
                <h2>{selected['symbol']}</h2><p>시장·업종·위험은 추천 순위를 바꾸지 않는 주문 전 확인 항목입니다.</p></div>
                <div class="score">{float(selected['weekly_similarity']):.2f}%
                <small>주봉 순위점수 · {_decision_label(str(validation.get('decision')))}</small></div></div>
                """,
                unsafe_allow_html=True,
            )
        st.page_link(
            "pages/9_Trading_Desk.py" if market_code == "kr" else "pages/12_US_Trading_Desk.py",
            label="주문관리 열기",
            icon="🛒",
            use_container_width=True,
        )
    finally:
        conn.close()


def _decision_label(value: str) -> str:
    return {
        "FINAL BUY": "매수 검토",
        "BUY WATCH": "관찰",
        "HOLD": "보류",
        "PASS": "제외",
    }.get(value, value)


def _style(st) -> None:
    st.markdown(
        """
        <style>
        .stApp{background:linear-gradient(135deg,#eef7ff,#f9fbff 48%,#eaf3ff);color:#13253a}
        .block-container{max-width:1600px;padding-top:1.3rem}
        .hero,.decision-card{display:flex;justify-content:space-between;align-items:center;padding:24px 28px;border:1px solid rgba(76,145,207,.23);border-radius:26px;background:rgba(255,255,255,.82);box-shadow:0 18px 50px rgba(63,105,145,.12);margin-bottom:16px}
        .hero h1,.decision-card h2{margin:3px 0}.hero p,.decision-card p{margin:5px 0;color:#647b92}.eyebrow{font-size:12px;letter-spacing:.15em;font-weight:800;color:#3479b9}
        .formula{padding:12px 16px;border-radius:999px;background:#eaf4ff;color:#286ba6;font-weight:800}.score{font-size:42px;font-weight:900;color:#0e6fc4;text-align:right}.score small{display:block;font-size:14px;color:#5f758b}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE recommendation validation")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()
    run(args.db)


if __name__ == "__main__":
    main()
