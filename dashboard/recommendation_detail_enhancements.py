from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from dashboard.recommendation_reason_panel import render_recommendation_reason_button
from dashboard.replay_analysis_panel import render_replay_analysis_panel


def _number(value: Any) -> float | None:
    try:
        if value is None or str(value) == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def render_recommendation_detail_enhancements(
    *,
    db_path: str,
    payload: dict[str, Any],
    selected: dict[str, Any],
    market: str,
    ticker: str,
    current: pd.DataFrame,
    current_label: str,
    include_heavy: bool,
) -> None:
    prediction = payload.get("prediction") if isinstance(payload.get("prediction"), dict) else {}
    st.markdown("### 추천 핵심정보")
    rows = []
    target_price = _number(payload.get("target_price") or payload.get("take_profit") or payload.get("expected_price"))
    stop_price = _number(payload.get("stop_loss") or payload.get("stop_price"))
    if target_price is not None:
        rows.append({"항목": "목표가", "값": f"{target_price:,.0f}"})
    if stop_price is not None:
        rows.append({"항목": "손절가", "값": f"{stop_price:,.0f}"})
    if prediction:
        target_return = _number(prediction.get("target_return"))
        stop_return = _number(prediction.get("stop_return"))
        holding_days = prediction.get("holding_days")
        rows.extend(
            [
                {"항목": "Prediction 등급", "값": str(prediction.get("grade") or "-")},
                {"항목": "목표수익", "값": f"{target_return:+.2f}%" if target_return is not None else "-"},
                {"항목": "참고 손절폭", "값": f"{stop_return:.2f}%" if stop_return is not None else "-"},
                {"항목": "권장 보유기간", "값": f"{int(holding_days)}거래일" if holding_days not in (None, "") else "-"},
            ]
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    render_recommendation_reason_button(
        payload=payload,
        selected=selected,
        market=market,
        ticker=ticker,
    )

    render_replay_analysis_panel(
        db_path=db_path,
        payload=payload,
        current=current,
        current_label=current_label,
        key_prefix=f"recommendation_detail_{market}_{ticker}",
        include_heavy=include_heavy,
    )

    if not include_heavy:
        st.info("가격·STO·미래경로 차트는 아래 상세 차트 버튼을 누르면 추가로 표시됩니다.")
