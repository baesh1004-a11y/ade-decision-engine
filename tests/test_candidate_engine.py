import pandas as pd

from strategy.candidate import evaluate_latest, score_latest


def _row(**overrides):
    base = {
        "Close": 100.0,
        "MA20": 95.0,
        "MA60": 90.0,
        "MA120": 80.0,
        "VOL20_RATIO": 6.0,
        "IS_BULLISH": True,
        "BODY_RATIO": 0.7,
        "STO533_K": 20.0,
        "STO533_D": 15.0,
        "STO1066_K": 35.0,
        "STO1066_D": 30.0,
        "STO201212_K": 45.0,
        "STO201212_D": 40.0,
    }
    base.update(overrides)
    return base


def test_candidate_engine_returns_structured_decision():
    df = pd.DataFrame([_row()])

    decision = evaluate_latest(df)

    assert decision.engine_version == "candidate-v0.2.0"
    assert decision.score >= 70
    assert decision.grade in {"A", "B"}
    assert decision.action in {"BUY_CANDIDATE", "WATCHLIST"}
    assert decision.risk_level == "LOW"
    assert decision.rule_hits


def test_score_latest_backward_compatible_dict():
    df = pd.DataFrame([_row()])

    decision = score_latest(df)

    assert isinstance(decision, dict)
    assert "score" in decision
    assert "reasons" in decision
    assert "close" in decision
    assert "risk_flags" in decision


def test_high_risk_for_bearish_candle_forces_watch():
    df = pd.DataFrame([
        _row(IS_BULLISH=False, BODY_RATIO=0.8, VOL20_RATIO=16.0)
    ])

    decision = evaluate_latest(df)

    assert decision.risk_level == "HIGH"
    assert decision.action == "WATCH"
    assert "Strong bearish candle body" in decision.risk_flags
    assert "Abnormal volume spike" in decision.risk_flags


def test_empty_dataframe_raises_value_error():
    df = pd.DataFrame([])

    try:
        evaluate_latest(df)
    except ValueError as exc:
        assert "empty dataframe" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
