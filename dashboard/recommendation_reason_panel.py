from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def _as_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _number(value: Any) -> float | None:
    try:
        if value is None or str(value) == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def render_recommendation_reason_button(
    *,
    payload: dict[str, Any],
    selected: dict[str, Any],
    market: str,
    ticker: str,
) -> None:
    """Render engine-native recommendation reasons behind an explicit detail button."""
    reasons = _as_text_list(payload.get("reasons"))
    prediction = payload.get("prediction") if isinstance(payload.get("prediction"), dict) else {}
    replay_matches = payload.get("replay_matches") if isinstance(payload.get("replay_matches"), list) else []

    state_key = f"ade_show_recommendation_reasons_{market}_{ticker}"
    st.session_state.setdefault(state_key, False)
    label = "추천근거 접기" if st.session_state[state_key] else "추천근거 보기"
    if st.button(label, key=f"recommendation_reason_button_{market}_{ticker}", use_container_width=True):
        st.session_state[state_key] = not st.session_state[state_key]
        st.rerun()

    if not st.session_state[state_key]:
        return

    with st.container(border=True):
        st.markdown("### 추천근거")
        if reasons:
            for index, reason in enumerate(reasons, start=1):
                st.markdown(f"**{index}.** {reason}")
        else:
            st.info("저장된 엔진 추천근거가 없습니다. 다음 추천 실행부터 표시됩니다.")

        threshold_rows = []
        weekly = _number(selected.get("weekly_similarity") or selected.get("final_similarity"))
        sto = _number(selected.get("sto_similarity"))
        if weekly is not None:
            threshold_rows.append({"항목": "주봉 유사도", "값": f"{weekly:.2f}%"})
        if sto is not None:
            threshold_rows.append({"항목": "STO 유사도", "값": f"{sto:.2f}%"})
        if replay_matches:
            threshold_rows.append({"항목": "Replay 사례", "값": f"{len(replay_matches)}건"})
        if prediction:
            grade = str(prediction.get("grade") or "-")
            probability = _number(prediction.get("seven_day_up_probability"))
            expected = _number(prediction.get("seven_day_expected_return"))
            target = _number(prediction.get("target_return"))
            stop = _number(prediction.get("stop_return"))
            holding = prediction.get("holding_days")
            threshold_rows.extend(
                [
                    {"항목": "Prediction 등급", "값": grade},
                    {"항목": "7일 상승확률", "값": f"{probability:.2f}%" if probability is not None else "-"},
                    {"항목": "7일 기대수익", "값": f"{expected:+.2f}%" if expected is not None else "-"},
                    {"항목": "목표수익", "값": f"{target:+.2f}%" if target is not None else "-"},
                    {"항목": "참고 손절폭", "값": f"{stop:.2f}%" if stop is not None else "-"},
                    {"항목": "권장 보유기간", "값": f"{int(holding)}거래일" if holding not in (None, "") else "-"},
                ]
            )

        if threshold_rows:
            st.dataframe(pd.DataFrame(threshold_rows), hide_index=True, use_container_width=True)

        st.caption("추천근거는 저장된 엔진 판단 원문과 부가 예측값을 그대로 보여주며, 추천 순위 계산식은 변경하지 않습니다.")
