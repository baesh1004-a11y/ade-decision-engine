from __future__ import annotations

import json
import sqlite3

import pandas as pd

from dashboard.recommendation_workbench_v2_app import _current_bars, _pattern_bars
from markets.profiles import get_market_profile
from recommendation.run_context import load_latest_context
from sto.structure_similarity import STOStructure, STOStructureSimilarityEngine


def render_sto_similarity_status() -> None:
    import streamlit as st

    market = _active_market(st.session_state)
    profile = get_market_profile(market)
    if not profile.db_path.exists():
        return

    selected_ticker = str(st.session_state.get(f"workbench_selected_{market}") or "").strip()
    if not selected_ticker:
        return

    conn = sqlite3.connect(str(profile.db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        context = load_latest_context(conn, profile.code, 50)
        if context is None:
            return
        selected = next(
            (dict(row) for row in context.recommendations if str(row["ticker"]) == selected_ticker),
            None,
        )
        if selected is None:
            return

        payload = _safe_json(selected.get("payload_json"))
        pattern = _selected_pattern(conn, payload)
        current = _current_bars(conn, profile.code, selected_ticker, profile.price_source)
        historical = _pattern_bars(conn, pattern)
        if current.empty or pattern is None:
            return

        engine = STOStructureSimilarityEngine()
        current_structure = engine.extract(current)
        historical_structure = _historical_structure(engine, pattern, historical)
        if historical_structure is None:
            return

        scores = {
            "단기 STO": _layer_similarity(engine, current_structure.short_path, historical_structure.short_path, current_structure.short, historical_structure.short),
            "중기 STO": _layer_similarity(engine, current_structure.middle_path, historical_structure.middle_path, current_structure.middle, historical_structure.middle),
            "장기 STO": _layer_similarity(engine, current_structure.long_path, historical_structure.long_path, current_structure.long, historical_structure.long),
            "Signal": _signal_similarity(engine, current_structure, historical_structure),
        }

        st.markdown("### STO 계층 유사도")
        st.caption("현재 종목과 선택된 과거 급등 직전 패턴의 최근 6주 STO 궤적을 계층별로 비교합니다.")
        cols = st.columns(4, gap="small")
        for col, (label, score) in zip(cols, scores.items()):
            emoji, text, tone = _status(score)
            col.markdown(
                f'<div class="sto-status-card {tone}"><span>{label}</span>'
                f'<strong>{emoji} {text}</strong><small>{score:.1f}%</small></div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            """
            <style>
            .sto-status-card{padding:13px 14px;border-radius:12px;border:1px solid #dbe6ef;background:#fff;margin:4px 0 12px}
            .sto-status-card span,.sto-status-card small{display:block;color:#718397}.sto-status-card strong{display:block;font-size:17px;margin:5px 0}
            .sto-status-card.good{border-left:5px solid #22a06b}.sto-status-card.warn{border-left:5px solid #e0a21a}.sto-status-card.bad{border-left:5px solid #d84a4a}
            </style>
            """,
            unsafe_allow_html=True,
        )
    finally:
        conn.close()


def _active_market(session_state) -> str:
    kr = str(session_state.get("workbench_selected_kr") or "").strip()
    us = str(session_state.get("workbench_selected_us") or "").strip()
    if us and not kr:
        return "us"
    return "kr"


def _safe_json(value) -> dict[str, object]:
    try:
        result = json.loads(str(value or "{}"))
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _selected_pattern(conn: sqlite3.Connection, payload: dict[str, object]):
    matches = payload.get("replay_matches") or []
    if not isinstance(matches, list) or not matches:
        return None
    event_id = str(matches[0].get("event_id") or "")
    if not event_id:
        return None
    row = conn.execute("SELECT * FROM surge_patterns WHERE pattern_id=?", (event_id,)).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM surge_patterns WHERE source_event_id=? ORDER BY surge_start_date DESC LIMIT 1",
            (event_id,),
        ).fetchone()
    return row


def _historical_structure(engine: STOStructureSimilarityEngine, pattern, historical: pd.DataFrame) -> STOStructure | None:
    raw = _safe_json(pattern["sto_json"] if "sto_json" in pattern.keys() else None)
    if raw:
        allowed = STOStructure.__dataclass_fields__.keys()
        values = {key: raw[key] for key in allowed if key in raw}
        try:
            return STOStructure(**values)
        except TypeError:
            pass
    if historical.empty:
        return None
    renamed = historical.rename(
        columns={"trade_date": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    )
    return engine.extract(renamed)


def _layer_similarity(engine: STOStructureSimilarityEngine, current_path, historical_path, current_value: float, historical_value: float) -> float:
    if current_path and historical_path and len(current_path) == len(historical_path):
        return round(engine._path_similarity(list(current_path), list(historical_path)), 2)
    distance = abs(float(current_value) - float(historical_value)) / 100.0
    return round(max(0.0, 100.0 / (1.0 + distance * 5.0)), 2)


def _signal_similarity(engine: STOStructureSimilarityEngine, current: STOStructure, historical: STOStructure) -> float:
    if current.arrangement == historical.arrangement:
        arrangement = 100.0
    elif engine._compatible(current.arrangement, historical.arrangement):
        arrangement = 55.0
    else:
        arrangement = 25.0
    structure = engine._feature_similarity(current.vector[3:6], historical.vector[3:6], scale=3.0)
    slope = engine._feature_similarity(current.vector[6:9], historical.vector[6:9], scale=6.0)
    return round(arrangement * 0.45 + structure * 0.30 + slope * 0.25, 2)


def _status(score: float) -> tuple[str, str, str]:
    if score >= 90.0:
        return "🟢", "매우 유사", "good"
    if score >= 80.0:
        return "🟢", "유사", "good"
    if score >= 65.0:
        return "🟡", "약간 차이", "warn"
    return "🔴", "차이", "bad"
