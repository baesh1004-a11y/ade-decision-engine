from strategy.probability import ProbabilityEngine, evaluate_probability


def _pattern_context(**overrides):
    base = {
        "ticker": "NVDA",
        "pattern_similarity": 0.84,
        "context_similarity": 0.78,
        "combined_similarity": 0.82,
        "expected_returns": {"return_20d": 0.06},
        "win_rates": {"win_rate_20d": 0.72},
        "risk_flags": [],
        "pattern": {
            "matches": [
                {"forward_returns": {"return_20d": 0.08}},
                {"forward_returns": {"return_20d": 0.04}},
                {"forward_returns": {"return_20d": -0.02}},
            ]
        },
    }
    base.update(overrides)
    return base


def test_strong_probability_can_recommend_strong_buy():
    decision = ProbabilityEngine(horizon_days=20).evaluate(_pattern_context())

    assert decision.engine_version == "probability-engine-v1.0.0"
    assert decision.ticker == "NVDA"
    assert decision.horizon == "20d"
    assert decision.upside_probability >= 0.60
    assert decision.expected_return == 0.06
    assert decision.recommendation in {"BUY", "STRONG_BUY"}


def test_negative_expected_return_recommends_avoid():
    decision = ProbabilityEngine(horizon_days=20).evaluate(
        _pattern_context(
            expected_returns={"return_20d": -0.03},
            win_rates={"win_rate_20d": 0.35},
            combined_similarity=0.65,
        )
    )

    assert decision.recommendation == "AVOID"
    assert "Negative expected return" in decision.risk_flags


def test_low_confidence_adds_risk_flag():
    decision = ProbabilityEngine(horizon_days=20).evaluate(
        _pattern_context(
            pattern_similarity=0.4,
            context_similarity=0.4,
            combined_similarity=0.4,
            risk_flags=["Low context similarity"],
            expected_returns={"return_20d": 0.01},
            win_rates={"win_rate_20d": 0.51},
        )
    )

    assert "Low probability confidence" in decision.risk_flags


def test_evaluate_probability_backward_compatible_dict():
    result = evaluate_probability(_pattern_context(), horizon_days=20)

    assert isinstance(result, dict)
    assert "upside_probability" in result
    assert "recommendation" in result


def test_invalid_horizon_raises_value_error():
    try:
        ProbabilityEngine(horizon_days=0)
    except ValueError as exc:
        assert "horizon_days" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
