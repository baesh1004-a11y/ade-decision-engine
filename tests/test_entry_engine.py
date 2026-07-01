import pandas as pd

from strategy.entry import EntryTimingEngine, evaluate_entry


def _rows(n=25, **last_overrides):
    rows = []
    for i in range(n):
        close = 100 + i * 0.5
        rows.append(
            {
                "Open": close - 0.5,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000 + i,
                "MA20": close - 2.0,
                "MA60": close - 5.0,
                "MA120": close - 10.0,
                "VOL20_RATIO": 1.2,
                "BODY_RATIO": 0.45,
                "IS_BULLISH": True,
                "STO533_K": 45.0,
                "STO533_D": 50.0,
                "RSI": 55.0,
                "MACD": 0.1,
                "MACD_SIGNAL": 0.2,
            }
        )
    rows[-2]["STO533_K"] = 35.0
    rows[-2]["STO533_D"] = 40.0
    rows[-2]["MACD"] = 0.1
    rows[-2]["MACD_SIGNAL"] = 0.2
    rows[-1].update(last_overrides)
    return pd.DataFrame(rows)


def _candidate(**overrides):
    base = {
        "score": 90,
        "grade": "A",
        "action": "BUY_CANDIDATE",
        "confidence": 0.90,
        "risk_level": "LOW",
    }
    base.update(overrides)
    return base


def _position(**overrides):
    base = {
        "recommended_weight": 0.10,
        "shares": 100,
    }
    base.update(overrides)
    return base


def test_breakout_with_volume_returns_buy_now():
    df = _rows(
        Close=113.0,
        High=114.0,
        MA20=110.0,
        MA60=105.0,
        MA120=100.0,
        VOL20_RATIO=2.2,
        STO533_K=45.0,
        STO533_D=40.0,
        MACD=0.3,
        MACD_SIGNAL=0.2,
        RSI=58.0,
    )

    decision = EntryTimingEngine().evaluate(
        df,
        candidate=_candidate(),
        position=_position(),
        market_regime="BULL",
    )

    assert decision.engine_version == "entry-timing-v1.0.0"
    assert decision.action == "BUY_NOW"
    assert decision.order_type == "LIMIT"
    assert decision.entry_score >= 80
    assert decision.limit_price == decision.entry_price


def test_pullback_support_returns_wait_or_buy_now():
    df = _rows(
        Close=110.5,
        High=111.5,
        Low=108.5,
        MA20=110.0,
        MA60=103.0,
        MA120=96.0,
        VOL20_RATIO=1.4,
        STO533_K=42.0,
        STO533_D=38.0,
        RSI=52.0,
    )
    df.loc[df.index[-5], "Close"] = 115.0

    decision = EntryTimingEngine().evaluate(
        df,
        candidate=_candidate(),
        position=_position(),
        market_regime="SIDEWAY",
    )

    assert decision.action in {"BUY_NOW", "WAIT"}
    assert any(hit["name"] == "pullback_support" for hit in decision.signal_hits)


def test_bear_market_reduces_score_and_can_wait():
    df = _rows(
        Close=113.0,
        High=114.0,
        MA20=110.0,
        MA60=105.0,
        MA120=100.0,
        VOL20_RATIO=2.0,
        STO533_K=45.0,
        STO533_D=40.0,
        MACD=0.3,
        MACD_SIGNAL=0.2,
    )

    decision = EntryTimingEngine().evaluate(
        df,
        candidate=_candidate(),
        position=_position(),
        market_regime="BEAR",
    )

    assert decision.entry_score < 100
    assert "Bear market entry discount required" in decision.risk_flags
    assert decision.action in {"WAIT", "WATCH", "BUY_NOW"}


def test_high_candidate_risk_cancels_entry():
    df = _rows(VOL20_RATIO=2.2, MACD=0.3, MACD_SIGNAL=0.2)

    decision = EntryTimingEngine().evaluate(
        df,
        candidate=_candidate(risk_level="HIGH"),
        position=_position(),
        market_regime="BULL",
    )

    assert decision.risk_level == "HIGH"
    assert decision.action == "CANCEL"


def test_no_executable_position_cancels_entry():
    df = _rows(VOL20_RATIO=2.2)

    decision = EntryTimingEngine().evaluate(
        df,
        candidate=_candidate(),
        position=_position(recommended_weight=0.0, shares=0),
        market_regime="BULL",
    )

    assert decision.action == "CANCEL"
    assert "No executable position size" in decision.risk_flags


def test_bearish_candle_blocks_immediate_entry():
    df = _rows(
        IS_BULLISH=False,
        BODY_RATIO=0.8,
        VOL20_RATIO=2.5,
        MACD=0.3,
        MACD_SIGNAL=0.2,
    )

    decision = EntryTimingEngine().evaluate(
        df,
        candidate=_candidate(),
        position=_position(),
        market_regime="BULL",
    )

    assert decision.risk_level == "HIGH"
    assert decision.action == "CANCEL"
    assert "Strong bearish candle blocks immediate entry" in decision.risk_flags


def test_standalone_entry_evaluation_without_candidate_or_position():
    df = _rows(
        Close=113.0,
        High=114.0,
        MA20=110.0,
        MA60=105.0,
        MA120=100.0,
        VOL20_RATIO=2.2,
        STO533_K=45.0,
        STO533_D=40.0,
        MACD=0.3,
        MACD_SIGNAL=0.2,
        RSI=58.0,
    )

    decision = EntryTimingEngine().evaluate(df, market_regime="BULL")

    assert decision.action in {"BUY_NOW", "WAIT", "WATCH"}
    assert decision.action != "CANCEL"


def test_evaluate_entry_backward_compatible_dict():
    df = _rows(VOL20_RATIO=2.2, MACD=0.3, MACD_SIGNAL=0.2)

    decision = evaluate_entry(
        df,
        candidate=_candidate(),
        position=_position(),
        market_regime="BULL",
    )

    assert isinstance(decision, dict)
    assert "entry_score" in decision
    assert "action" in decision
    assert "signal_hits" in decision


def test_empty_dataframe_raises_value_error():
    try:
        EntryTimingEngine().evaluate(pd.DataFrame([]))
    except ValueError as exc:
        assert "empty dataframe" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_short_dataframe_raises_value_error():
    try:
        EntryTimingEngine().evaluate(_rows(n=5))
    except ValueError as exc:
        assert "at least 20 rows" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
