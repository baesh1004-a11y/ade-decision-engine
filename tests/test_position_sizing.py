from strategy.position_sizing import (
    AccountState,
    PositionSizingEngine,
    PositionSizingInput,
    recommend_position,
)


def _engine() -> PositionSizingEngine:
    return PositionSizingEngine()


def test_a_grade_high_confidence_bull_market_recommends_expected_range():
    payload = PositionSizingInput(
        ticker="NVDA",
        price=100.0,
        grade="A",
        confidence=0.92,
        risk_level="LOW",
        atr=2.0,
        market_regime="BULL",
        account=AccountState(account_balance=100_000_000, cash=100_000_000),
    )

    result = _engine().recommend(payload)

    assert result.engine_version == "position-sizing-v1.0.0"
    assert 0.12 <= result.recommended_weight <= 0.13
    assert result.shares > 0
    assert result.buy_amount > 0
    assert result.risk_score < 30


def test_bear_market_reduces_position_size():
    payload = PositionSizingInput(
        ticker="NVDA",
        price=100.0,
        grade="A",
        confidence=0.95,
        risk_level="LOW",
        atr=2.0,
        market_regime="BEAR",
        account=AccountState(account_balance=100_000_000, cash=100_000_000),
    )

    result = _engine().recommend(payload)

    assert 0.06 <= result.recommended_weight <= 0.07


def test_high_atr_reduces_position_size():
    low_vol = PositionSizingInput(
        ticker="LOWVOL",
        price=100.0,
        grade="A",
        confidence=0.90,
        atr=2.0,
        market_regime="BULL",
        account=AccountState(account_balance=100_000_000, cash=100_000_000),
    )
    high_vol = PositionSizingInput(
        ticker="HIGHVOL",
        price=100.0,
        grade="A",
        confidence=0.90,
        atr=9.0,
        market_regime="BULL",
        account=AccountState(account_balance=100_000_000, cash=100_000_000),
    )

    low_result = _engine().recommend(low_vol)
    high_result = _engine().recommend(high_vol)

    assert high_result.recommended_weight < low_result.recommended_weight
    assert high_result.atr_risk >= 0.08


def test_sector_exposure_blocks_new_buy_when_limit_exceeded():
    payload = PositionSizingInput(
        ticker="SOXL",
        price=100.0,
        grade="A",
        confidence=0.92,
        market_regime="BULL",
        account=AccountState(
            account_balance=100_000_000,
            cash=100_000_000,
            sector_exposure=0.35,
        ),
    )

    result = _engine().recommend(payload)

    assert result.recommended_weight == 0
    assert result.shares == 0
    assert result.sector_adjustment == 0


def test_stop_loss_caps_max_loss_to_one_percent_risk_budget():
    payload = PositionSizingInput(
        ticker="TSLA",
        price=100.0,
        grade="S",
        confidence=0.95,
        risk_level="LOW",
        stop_loss_price=90.0,
        market_regime="BULL",
        account=AccountState(account_balance=100_000_000, cash=100_000_000),
    )

    result = _engine().recommend(payload)

    assert result.max_loss <= 1_000_000
    assert result.recommended_weight <= 0.10


def test_dict_payload_backward_compatible():
    result = recommend_position(
        {
            "ticker": "NVDA",
            "price": 100.0,
            "grade": "B",
            "confidence": 0.80,
            "market_regime": "SIDEWAY",
            "account": {
                "account_balance": 50_000_000,
                "cash": 10_000_000,
            },
        }
    )

    assert isinstance(result, dict)
    assert result["ticker"] == "NVDA"
    assert "recommended_weight" in result
    assert "shares" in result


def test_invalid_inputs_raise_value_error():
    payload = PositionSizingInput(
        ticker="BAD",
        price=0,
        grade="A",
        confidence=0.90,
        account=AccountState(account_balance=100_000_000),
    )

    try:
        _engine().recommend(payload)
    except ValueError as exc:
        assert "price" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
