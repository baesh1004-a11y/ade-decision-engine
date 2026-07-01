from strategy.risk import RiskEngine, RiskInput, evaluate_risk


def _engine() -> RiskEngine:
    return RiskEngine()


def test_low_risk_allows_trading():
    decision = _engine().evaluate(
        RiskInput(
            account_balance=100_000_000,
            equity_peak=102_000_000,
            daily_pnl=500_000,
            portfolio_heat=0.02,
            cash_weight=0.20,
            vix=18,
            market_regime="SIDEWAY",
        )
    )

    assert decision.engine_version == "risk-engine-v1.0.0"
    assert decision.risk_level == "LOW"
    assert decision.action == "ALLOW_TRADING"
    assert decision.trade_allowed is True
    assert decision.max_new_position_weight == 0.10


def test_daily_stop_loss_pauses_trading():
    decision = _engine().evaluate(
        RiskInput(
            account_balance=100_000_000,
            equity_peak=105_000_000,
            daily_pnl=-3_500_000,
        )
    )

    assert decision.risk_level == "CRITICAL"
    assert decision.action == "PAUSE_TRADING"
    assert decision.trade_allowed is False
    assert "Daily stop loss breached" in decision.risk_flags


def test_max_drawdown_stop_forces_deleverage():
    decision = _engine().evaluate(
        RiskInput(
            account_balance=84_000_000,
            equity_peak=100_000_000,
            daily_pnl=-500_000,
        )
    )

    assert decision.risk_level == "CRITICAL"
    assert decision.action == "FORCE_DELEVERAGE"
    assert decision.target_cash_weight >= 0.70
    assert "Max drawdown stop breached" in decision.risk_flags


def test_drawdown_warning_reduces_risk():
    decision = _engine().evaluate(
        RiskInput(
            account_balance=89_000_000,
            equity_peak=100_000_000,
            daily_pnl=-500_000,
        )
    )

    assert "Max drawdown warning" in decision.risk_flags
    assert decision.action in {"REDUCE_RISK", "LIMIT_NEW_TRADES"}


def test_vix_crisis_forces_deleverage():
    decision = _engine().evaluate(
        RiskInput(
            account_balance=100_000_000,
            equity_peak=100_000_000,
            vix=42,
        )
    )

    assert decision.risk_level == "CRITICAL"
    assert decision.action == "FORCE_DELEVERAGE"
    assert "VIX crisis regime" in decision.risk_flags


def test_portfolio_heat_limits_new_trades():
    decision = _engine().evaluate(
        RiskInput(
            account_balance=100_000_000,
            equity_peak=100_000_000,
            portfolio_heat=0.07,
        )
    )

    assert "Portfolio heat limit breached" in decision.risk_flags
    assert decision.max_new_position_weight <= 0.06


def test_bear_market_raises_cash_target():
    decision = _engine().evaluate(
        RiskInput(
            account_balance=100_000_000,
            equity_peak=100_000_000,
            market_regime="BEAR",
        )
    )

    assert "Bear market regime" in decision.risk_flags
    assert decision.target_cash_weight >= 0.50


def test_consecutive_losses_reduce_trading_intensity():
    decision = _engine().evaluate(
        RiskInput(
            account_balance=100_000_000,
            equity_peak=100_000_000,
            consecutive_losses=3,
        )
    )

    assert "Consecutive loss streak" in decision.risk_flags


def test_dict_payload_backward_compatible():
    decision = evaluate_risk(
        {
            "account_balance": 100_000_000,
            "equity_peak": 100_000_000,
            "daily_pnl": 0,
            "vix": 20,
        }
    )

    assert isinstance(decision, dict)
    assert "risk_score" in decision
    assert "action" in decision


def test_invalid_account_balance_raises_value_error():
    try:
        _engine().evaluate(RiskInput(account_balance=0, equity_peak=100_000_000))
    except ValueError as exc:
        assert "account_balance" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_negative_consecutive_losses_raises_value_error():
    try:
        _engine().evaluate(
            RiskInput(account_balance=100_000_000, equity_peak=100_000_000, consecutive_losses=-1)
        )
    except ValueError as exc:
        assert "consecutive_losses" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
