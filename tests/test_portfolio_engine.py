from strategy.portfolio import Holding, PortfolioManagerEngine, PortfolioState, evaluate_portfolio


def _engine() -> PortfolioManagerEngine:
    return PortfolioManagerEngine()


def test_balanced_portfolio_holds():
    portfolio = PortfolioState(
        account_balance=100_000_000,
        cash=20_000_000,
        market_regime="SIDEWAY",
        holdings=[
            Holding("NVDA", "US", "SEMICONDUCTOR", 1, 20_000_000),
            Holding("AAPL", "US", "TECH", 1, 20_000_000),
            Holding("JPM", "US", "FINANCIAL", 1, 20_000_000),
            Holding("005930", "KR", "ELECTRONICS", 1, 20_000_000),
        ],
    )

    decision = _engine().evaluate(portfolio)

    assert decision.engine_version == "portfolio-manager-v1.0.0"
    assert decision.action == "HOLD"
    assert decision.portfolio_score >= 85
    assert not decision.recommendations


def test_single_position_overweight_recommends_trim():
    portfolio = PortfolioState(
        account_balance=100_000_000,
        cash=10_000_000,
        market_regime="BULL",
        holdings=[
            Holding("NVDA", "US", "SEMICONDUCTOR", 1, 35_000_000),
            Holding("AAPL", "US", "TECH", 1, 15_000_000),
        ],
    )

    decision = _engine().evaluate(portfolio)

    assert decision.action == "REBALANCE"
    assert any(rec["ticker"] == "NVDA" and rec["action"] == "TRIM" for rec in decision.recommendations)
    assert "NVDA overweight" in decision.risk_flags


def test_bear_market_requires_more_cash():
    portfolio = PortfolioState(
        account_balance=100_000_000,
        cash=10_000_000,
        market_regime="BEAR",
        holdings=[
            Holding("NVDA", "US", "SEMICONDUCTOR", 1, 20_000_000),
            Holding("AAPL", "US", "TECH", 1, 20_000_000),
        ],
    )

    decision = _engine().evaluate(portfolio)

    assert "Cash below target" in decision.risk_flags
    assert any(rec["action"] == "RAISE_CASH" for rec in decision.recommendations)


def test_high_cash_recommends_deploy_cash():
    portfolio = PortfolioState(
        account_balance=100_000_000,
        cash=80_000_000,
        market_regime="BULL",
        holdings=[Holding("NVDA", "US", "SEMICONDUCTOR", 1, 10_000_000)],
    )

    decision = _engine().evaluate(portfolio)

    assert "Cash above target" in decision.risk_flags
    assert any(rec["action"] == "DEPLOY_CASH" for rec in decision.recommendations)


def test_sector_overweight_flagged():
    portfolio = PortfolioState(
        account_balance=100_000_000,
        cash=10_000_000,
        market_regime="SIDEWAY",
        holdings=[
            Holding("NVDA", "US", "SEMICONDUCTOR", 1, 20_000_000),
            Holding("AMD", "US", "SEMICONDUCTOR", 1, 20_000_000),
            Holding("TSM", "US", "SEMICONDUCTOR", 1, 15_000_000),
        ],
    )

    decision = _engine().evaluate(portfolio)

    assert "SEMICONDUCTOR sector overweight" in decision.risk_flags
    assert decision.sector_weights["SEMICONDUCTOR"] > 0.30


def test_too_many_positions_flagged():
    holdings = [Holding(f"T{i}", "US", "TECH", 1, 1_000_000) for i in range(11)]
    portfolio = PortfolioState(account_balance=100_000_000, cash=20_000_000, holdings=holdings)

    decision = _engine().evaluate(portfolio)

    assert "Too many positions" in decision.risk_flags


def test_dict_payload_backward_compatible():
    decision = evaluate_portfolio(
        {
            "account_balance": 100_000_000,
            "cash": 20_000_000,
            "market_regime": "SIDEWAY",
            "holdings": [
                {"ticker": "NVDA", "market": "US", "sector": "SEMICONDUCTOR", "quantity": 1, "price": 10_000_000}
            ],
        }
    )

    assert isinstance(decision, dict)
    assert "portfolio_score" in decision
    assert "recommendations" in decision


def test_invalid_account_balance_raises_value_error():
    try:
        _engine().evaluate(PortfolioState(account_balance=0, cash=0, holdings=[]))
    except ValueError as exc:
        assert "account_balance" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_negative_holding_price_raises_value_error():
    try:
        _engine().evaluate(
            PortfolioState(
                account_balance=100_000_000,
                cash=10_000_000,
                holdings=[Holding("BAD", "US", "TECH", 1, -1)],
            )
        )
    except ValueError as exc:
        assert "price" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
