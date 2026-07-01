import pandas as pd

from calibration.calibrator import ProbabilityCalibrator
from calibration.models import ProbabilityObservation
from calibration.persistence import CalibrationRepository
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
        vix=18,
    )

    result = ADEPipeline().run(context)

    assert "pattern_memory" in result.decisions
    assert result.decisions["pattern_memory"]["records"] > 0
    assert "pattern_context" in result.decisions
    assert "pattern" in result.decisions
    assert result.decisions["pattern"]["engine_version"] == "pattern-memory-matching-v1.0.0"
    assert "probability" in result.decisions
    assert result.decisions["probability"]["calibration"]["applied"] is False
    assert "candidate" in result.decisions
    assert "risk" in result.decisions
    assert "position" in result.decisions
    assert "entry" in result.decisions
    assert "explanation" in result.decisions
    assert result.decisions["explanation"]["engine_version"] == "explainable-ai-v1.0.0"
    assert result.decisions["explanation"]["ticker"] == "NVDA"
    assert "probability_adjustment" in result.decisions["candidate"]
    assert result.decisions["risk"]["trade_allowed"] is True
    assert result.errors == []


def test_pipeline_applies_latest_calibration_table():
    repo = CalibrationRepository()
    observations = [
        ProbabilityObservation("NVDA", "2024-01-01", "20d", 0.8, 0),
        ProbabilityObservation("NVDA", "2024-01-02", "20d", 0.82, 0),
        ProbabilityObservation("NVDA", "2024-01-03", "20d", 0.75, 1),
        ProbabilityObservation("NVDA", "2024-01-04", "20d", 0.65, 1),
    ]
    table = ProbabilityCalibrator(bin_size=0.2).fit(observations).to_dict()
    repo.save_calibration_table(table)

    context = DecisionContext(
        market="us",
        ticker="NVDA",
        market_data=_market_data(),
        account_balance=100_000_000,
        cash=50_000_000,
        equity_peak=100_000_000,
        market_regime="BULL",
        vix=18,
    )

    result = ADEPipeline(calibration_repository=repo).run(context)

    assert result.decisions["probability"]["calibration"]["applied"] is True
    assert "raw_upside_probability" in result.decisions["probability"]
    assert result.decisions["candidate"]["probability_adjustment"]["calibration_applied"] is True
    assert result.decisions["explanation"]["metadata"]["evidence_count"] > 0
    repo.close()


def test_pipeline_risk_limits_position_size():
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
    assert result.decisions["risk"]["max_new_position_weight"] <= 0.06
    assert result.decisions["position"]["recommended_weight"] <= result.decisions["risk"]["max_new_position_weight"]


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
    assert "explanation" in result.decisions
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
    assert "pattern_memory" in result["decisions"]
    assert "pattern_context" in result["decisions"]
    assert "probability" in result["decisions"]
    assert "candidate" in result["decisions"]
    assert "risk" in result["decisions"]
    assert "explanation" in result["decisions"]
