import pandas as pd

from candidate_rules.engine import CandidateRuleScoreEngine
from online_learning.orchestrator import OnlineLearningOrchestrator
from calibration.persistence import CalibrationRepository
from learning_v2.models import RuleSample
from learning_v2.persistence import LearningV2Repository
from strategy_library.engine import StrategyLibraryEngine
from timeframe.engine import MultiTimeframeEngine


def _market_data(rows: int = 120) -> pd.DataFrame:
    data = []
    for i in range(rows):
        close = 100 + i * 0.4
        data.append(
            {
                "Date": f"2024-01-{(i % 28) + 1:02d}",
                "Open": close - 0.2,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000 + i * 1000,
            }
        )
    df = pd.DataFrame(data)
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA60"] = df["Close"].rolling(60).mean()
    df["VOL20_RATIO"] = df["Volume"] / df["Volume"].rolling(20).mean()
    return df


def test_candidate_rule_score_engine_outputs_rule_scores():
    result = CandidateRuleScoreEngine().evaluate(
        _market_data(),
        pattern_context={"combined_similarity": 0.78},
        probability={"upside_probability": 0.64, "expected_return": 0.04},
        rule_weights={"probability": 1.2, "pattern": 1.1},
    ).to_dict()

    assert result["engine_version"] == "candidate-rule-score-v1.0.0"
    assert "rule_scores" in result
    assert "probability" in result["rule_scores"]
    assert 0 <= result["total_score"] <= 100


def test_strategy_library_evaluates_multiple_strategies():
    result = StrategyLibraryEngine().evaluate(_market_data())

    assert result["engine_version"] == "strategy-library-v1.0.0"
    assert "best_strategy" in result
    assert len(result["signals"]) >= 5
    assert "breakout" in result["strategy_scores"]


def test_multi_timeframe_engine_outputs_alignment():
    result = MultiTimeframeEngine().evaluate(_market_data())

    assert result["engine_version"] == "multi-timeframe-v1.0.0"
    assert result["signal"] in {"ALIGNED", "MIXED", "WEAK", "INSUFFICIENT"}
    assert "daily" in result["frames"]


def test_online_learning_orchestrator_runs_update():
    calibration_repo = CalibrationRepository()
    learning_repo = LearningV2Repository()
    backtest_result = {
        "ticker": "NVDA",
        "trades": [
            {
                "ticker": "NVDA",
                "entry_date": "2024-01-01",
                "gross_return": 0.05,
                "metadata": {
                    "candidate": {
                        "probability_adjustment": {
                            "upside_probability": 0.7,
                            "expected_return": 0.04,
                        }
                    }
                },
            }
        ],
    }

    result = OnlineLearningOrchestrator(calibration_repo, learning_repo).run_daily_update(
        backtest_result,
        rule_samples=[RuleSample("probability", True, 0.05), RuleSample("pattern", True, -0.01)],
    )

    assert result["engine_version"] == "online-learning-v1.0.0"
    assert result["status"] == "UPDATED"
    assert result["observation_count"] == 1
    calibration_repo.close()
    learning_repo.close()
