import pandas as pd

from strategy.exit import ExitDecisionEngine, PositionState, evaluate_exit


def _rows(**last_overrides):
    rows = []
    for i in range(5):
        close = 100 + i
        rows.append(
            {
                "Open": close - 0.5,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "MA20": close - 1.0,
                "MA60": close - 3.0,
                "MA120": close - 6.0,
                "ATR": 2.0,
                "RSI": 55.0,
                "MACD": 0.3,
                "MACD_SIGNAL": 0.2,
                "VOL20_RATIO": 1.0,
                "BODY_RATIO": 0.4,
                "IS_BULLISH": True,
            }
        )
    rows[-2]["MACD"] = 0.3
    rows[-2]["MACD_SIGNAL"] = 0.2
    rows[-1].update(last_overrides)
    return pd.DataFrame(rows)


def _position(**overrides):
    base = {
        "ticker": "NVDA",
        "entry_price": 100.0,
        "shares": 100,
        "highest_price": 110.0,
        "holding_days": 10,
    }
    base.update(overrides)
    return PositionState(**base)


def test_profit_10_triggers_partial_sell():
    df = _rows(Close=110.0, High=111.0, RSI=65.0)

    decision = ExitDecisionEngine().evaluate(df, _position(current_price=110.0))

    assert decision.engine_version == "exit-decision-v1.0.0"
    assert decision.action == "SELL_25"
    assert decision.sell_shares == 25
    assert decision.remaining_shares == 75
    assert decision.pnl_pct == 0.1


def test_profit_20_triggers_sell_all():
    df = _rows(Close=121.0, High=122.0, RSI=70.0)

    decision = ExitDecisionEngine().evaluate(df, _position(current_price=121.0, highest_price=122.0))

    assert decision.action == "SELL_ALL"
    assert decision.sell_ratio == 1.0
    assert decision.sell_shares == 100


def test_loss_5_triggers_hard_stop_sell_all():
    df = _rows(Close=94.0, High=96.0, Low=93.0)

    decision = ExitDecisionEngine().evaluate(df, _position(current_price=94.0))

    assert decision.action == "SELL_ALL"
    assert decision.risk_level == "HIGH"
    assert "Hard stop loss triggered" in decision.risk_flags


def test_atr_stop_triggers_sell_all():
    df = _rows(Close=95.5, High=97.0, Low=95.0, ATR=3.0)

    decision = ExitDecisionEngine().evaluate(df, _position(current_price=93.5))

    assert decision.action == "SELL_ALL"
    assert "ATR stop triggered" in decision.risk_flags


def test_trailing_stop_triggers_sell_all():
    df = _rows(Close=106.0, High=107.0, Low=105.0, ATR=3.0)

    decision = ExitDecisionEngine().evaluate(
        df,
        _position(current_price=103.0, highest_price=110.0),
    )

    assert decision.action == "SELL_ALL"
    assert "Trailing stop triggered" in decision.risk_flags


def test_macd_dead_cross_adds_exit_signal():
    df = _rows(Close=105.0, MACD=0.1, MACD_SIGNAL=0.2)
    df.loc[df.index[-2], "MACD"] = 0.3
    df.loc[df.index[-2], "MACD_SIGNAL"] = 0.2

    decision = ExitDecisionEngine().evaluate(df, _position(current_price=105.0))

    assert any(hit["name"] == "macd_dead_cross" for hit in decision.signal_hits)


def test_rsi_overheated_profit_can_sell_50_when_combined():
    df = _rows(Close=112.0, High=113.0, RSI=82.0, MACD=0.1, MACD_SIGNAL=0.2)
    df.loc[df.index[-2], "MACD"] = 0.3
    df.loc[df.index[-2], "MACD_SIGNAL"] = 0.2

    decision = ExitDecisionEngine().evaluate(df, _position(current_price=112.0, highest_price=113.0))

    assert decision.action in {"SELL_25", "SELL_50"}
    assert any(hit["name"] == "rsi_overheated" for hit in decision.signal_hits)


def test_time_exit_for_underperforming_position():
    df = _rows(Close=101.0, High=102.0, RSI=50.0, ATR=10.0)

    decision = ExitDecisionEngine().evaluate(
        df,
        _position(current_price=101.0, holding_days=35, highest_price=105.0),
    )

    assert any(hit["name"] == "time_exit_30" for hit in decision.signal_hits)
    assert decision.action in {"WATCH", "SELL_25"}


def test_gap_down_triggers_high_risk():
    df = _rows(Open=94.0, Close=95.0, High=96.0, Low=93.0)
    df.loc[df.index[-2], "Close"] = 100.0

    decision = ExitDecisionEngine().evaluate(df, _position(current_price=95.0))

    assert decision.risk_level == "HIGH"
    assert "Gap-down risk detected" in decision.risk_flags
    assert decision.action == "SELL_ALL"


def test_candidate_deterioration_adds_signal():
    df = _rows(Close=104.0)

    decision = ExitDecisionEngine().evaluate(
        df,
        _position(current_price=104.0),
        candidate={"score": 40, "risk_level": "MEDIUM"},
    )

    assert any(hit["name"] == "candidate_deterioration" for hit in decision.signal_hits)


def test_evaluate_exit_backward_compatible_dict():
    df = _rows(Close=110.0)

    decision = evaluate_exit(
        df,
        {
            "ticker": "NVDA",
            "entry_price": 100.0,
            "shares": 100,
            "current_price": 110.0,
            "highest_price": 111.0,
            "holding_days": 10,
        },
    )

    assert isinstance(decision, dict)
    assert decision["ticker"] == "NVDA"
    assert "sell_score" in decision
    assert "action" in decision


def test_invalid_position_raises_value_error():
    df = _rows()

    try:
        ExitDecisionEngine().evaluate(df, _position(entry_price=0))
    except ValueError as exc:
        assert "entry_price" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_empty_dataframe_raises_value_error():
    try:
        ExitDecisionEngine().evaluate(pd.DataFrame([]), _position())
    except ValueError as exc:
        assert "empty dataframe" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
