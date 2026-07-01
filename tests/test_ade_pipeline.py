import pandas as pd

from core.context import DecisionContext
from core.pipeline import ADEPipeline


def _market_data(rows: int = 160) -> pd.DataFrame:
    data = []
    for i in range(rows):
        close = 100 + i * 0.5
        data.append(
            {
                "Open": close - 0.3,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000,
            }
        )
    data[-1]["Open"] = data[-1]["Close"] - 2.0
    data[-1]["Volume"] = 3_000_000
    return pd.DataFrame(data)


def test_pipeline_runs_core_decision_chain():
    context = DecisionContext(
        market="us",
        ticker="NVDA",
        market_data=_market_data(),
        account_balance=100_000_000,
        cash=50_000_000,
        equity_peak=100_000_000,
        market_regime="BULL",
    )

    result = ADEPipeline().run(context)

    assert "candidate" in result.decisions
    assert "risk" in result.decisions
    assert "position" in result.decisions
    assert "entry" in result.decisions
    assert result.decisions["risk"]["trade_allowed"] is True
    assert result.errors == []


def test_pipeline_risk_caps_position_size():
    context = DecisionContext(
        market="us",
        ticker="NVDA",
        market_data=_market_data(),
        account_balance=100_000_000,
        cash=100_000_000,
        equity_peak=100_000_000,
        market_regime="SIDEWAY",
        portfolio_heat=0.07,
    )

    result = ADEPipeline().run(context)

    assert result.decisions["risk"]["action"] == "LIMIT_NEW_TRADES"
    assert result.decisions["position"]["recommended_weight"] <= result.decisions["risk"]["max_new_position_weight"]
    assert result.decisions["position"].get("risk_capped") is True


def test_pipeline_runs_optional_exit_portfolio_learning():
    context = DecisionContext(
        market="us",
        ticker="NVDA",
        market_data=_market_data(),
        account_balance=100_000_000,
        cash=20_000_000,
        equity_peak=105_000_000,
        market_regime="SIDEWAY",
        current_position={
            "entry_price": 100.0,
            "shares": 100,
            "highest_price": 180.0,
            "holding_days": 20,
        },
        holdings=[
            {"ticker": "NVDA", "market": "US", "sector": "SEMICONDUCTOR", "quantity": 1, "price": 20_000_000},
            {"ticker": "AAPL", "market": "US", "sector": "TECH", "quantity": 1, "price": 20_000_000},
            {"ticker": "005930", "market": "KR", "sector": "ELECTRONICS", "quantity": 1, "price": 20_000_000},
        ],
        learning_samples=[
            {"engine": "candidate", "rule": "trend", "action": "BUY", "expected_return": 0.01, "realized_return": 0.03},
            {"engine": "candidate", "rule": "trend", "action": "BUY", "expected_return": 0.01, "realized_return": 0.02},
            {"engine": "candidate", "rule": "trend", "action": "BUY", "expected_return": 0.01, "realized_return": 0.04},
            {"engine": "candidate", "rule": "trend", "action": "BUY", "expected_return": 0.01, "realized_return": 0.05},
            {"engine": "candidate", "rule": "trend", "action": "BUY", "expected_return": 0.01, "realized_return": 0.02},
        ],
    )

    result = ADEPipeline().run(context)

    assert "exit" in result.decisions
    assert "portfolio" in result.decisions
    assert "learning" in result.decisions
    assert result.errors == []


def test_context_serializes_pipeline_result():
    context = DecisionContext(
        market="us",
        ticker="NVDA",
        market_data=_market_data(),
        account_balance=100_000_000,
        cash=50_000_000,
    )

    result = ADEPipeline().run(context).to_dict()

    assert result["ticker"] == "NVDA"
    assert "candidate" in result["decisions"]
    assert "risk" in result["decisions"]
