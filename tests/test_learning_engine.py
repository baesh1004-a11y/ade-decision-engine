from strategy.learning import LearningEngine, LearningSample, evaluate_learning


def _engine() -> LearningEngine:
    return LearningEngine(min_samples=3)


def test_strong_rule_gets_boost_recommendation():
    samples = [
        LearningSample("candidate", "trend_alignment", "BUY", 0.02, 0.05),
        LearningSample("candidate", "trend_alignment", "BUY", 0.02, 0.03),
        LearningSample("candidate", "trend_alignment", "BUY", 0.02, 0.04),
    ]

    decision = _engine().evaluate(samples)

    assert decision.engine_version == "learning-engine-v1.0.0"
    assert decision.action == "APPLY_CONSERVATIVE_BOOST"
    assert "candidate:trend_alignment" in decision.strong_rules
    assert decision.recommendations[0]["recommendation"] == "BOOST_WEIGHT"


def test_weak_rule_gets_review_off_recommendation():
    samples = [
        LearningSample("entry", "breakout", "BUY", 0.02, -0.03),
        LearningSample("entry", "breakout", "BUY", 0.02, -0.02),
        LearningSample("entry", "breakout", "BUY", 0.02, 0.01),
    ]

    decision = _engine().evaluate(samples)

    assert decision.action == "REVIEW_RULES"
    assert "entry:breakout" in decision.weak_rules
    assert decision.recommendations[0]["recommendation"] == "REVIEW_OFF"


def test_negative_alpha_reduces_weight():
    samples = [
        LearningSample("exit", "rsi_overheated", "SELL", 0.05, 0.02),
        LearningSample("exit", "rsi_overheated", "SELL", 0.04, 0.02),
        LearningSample("exit", "rsi_overheated", "SELL", 0.03, 0.02),
    ]

    decision = _engine().evaluate(samples)

    assert decision.action == "REVIEW_RULES"
    assert decision.recommendations[0]["recommendation"] == "REDUCE_WEIGHT"


def test_insufficient_samples_keeps_collecting():
    samples = [
        LearningSample("risk", "vix_high", "REDUCE", 0.00, 0.01),
        LearningSample("risk", "vix_high", "REDUCE", 0.00, 0.02),
    ]

    decision = _engine().evaluate(samples)

    assert decision.action == "KEEP_CURRENT_RULES"
    assert decision.recommendations[0]["recommendation"] == "KEEP_COLLECTING"


def test_multiple_rules_are_grouped_independently():
    samples = [
        LearningSample("candidate", "trend", "BUY", 0.01, 0.03),
        LearningSample("candidate", "trend", "BUY", 0.01, 0.02),
        LearningSample("candidate", "trend", "BUY", 0.01, 0.04),
        LearningSample("entry", "gap_up", "WAIT", 0.02, -0.02),
        LearningSample("entry", "gap_up", "WAIT", 0.02, -0.01),
        LearningSample("entry", "gap_up", "WAIT", 0.02, -0.03),
    ]

    decision = _engine().evaluate(samples)

    assert len(decision.recommendations) == 2
    assert "candidate:trend" in decision.strong_rules
    assert "entry:gap_up" in decision.weak_rules


def test_dict_payload_backward_compatible():
    decision = evaluate_learning(
        [
            {"engine": "candidate", "rule": "trend", "action": "BUY", "expected_return": 0.01, "realized_return": 0.03},
            {"engine": "candidate", "rule": "trend", "action": "BUY", "expected_return": 0.01, "realized_return": 0.02},
            {"engine": "candidate", "rule": "trend", "action": "BUY", "expected_return": 0.01, "realized_return": 0.04},
            {"engine": "candidate", "rule": "trend", "action": "BUY", "expected_return": 0.01, "realized_return": 0.02},
            {"engine": "candidate", "rule": "trend", "action": "BUY", "expected_return": 0.01, "realized_return": 0.05},
        ]
    )

    assert isinstance(decision, dict)
    assert "learning_score" in decision
    assert "recommendations" in decision


def test_empty_samples_raise_value_error():
    try:
        _engine().evaluate([])
    except ValueError as exc:
        assert "at least one sample" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_negative_holding_days_raise_value_error():
    try:
        _engine().evaluate(
            [LearningSample("candidate", "trend", "BUY", 0.01, 0.02, holding_days=-1)]
        )
    except ValueError as exc:
        assert "holding_days" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
