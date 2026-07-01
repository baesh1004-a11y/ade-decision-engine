import pandas as pd

from backtest.simulator import BacktestConfig, BacktestSimulator
from calibration.calibrator import ProbabilityCalibrator
from calibration.collector import CalibrationCollector
from calibration.persistence import CalibrationRepository
from core.context import DecisionContext
from core.pipeline import ADEPipeline
from learning_v2.engine import AdaptiveLearningEngineV2
from learning_v2.models import RuleSample
from learning_v2.persistence import LearningV2Repository
from report.engine import ReportEngine


def _market_data(rows: int = 180) -> pd.DataFrame:
    data = []
    for i in range(rows):
        close = 100 + i * 0.35 + (i % 10) * 0.15
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
    return pd.DataFrame(data)


def test_e2e_decision_backtest_calibration_learning_report_flow():
    df = _market_data()

    # 1. Initial decision pipeline
    context = DecisionContext(
        market="us",
        ticker="NVDA",
        market_data=df,
        account_balance=100_000_000,
        cash=50_000_000,
        equity_peak=100_000_000,
        market_regime="BULL",
        vix=18,
    )
    pipeline_result = ADEPipeline().run(context)

    assert "candidate" in pipeline_result.decisions
    assert "probability" in pipeline_result.decisions
    assert "explanation" in pipeline_result.decisions
    assert "score_trace" in pipeline_result.decisions["candidate"]

    # 2. Backtest
    backtest_result = BacktestSimulator(
        BacktestConfig(
            market="us",
            ticker="NVDA",
            initial_cash=100_000_000,
            min_history=100,
            max_holding_days=20,
            buy_score_threshold=40,
            buy_weight=0.10,
        )
    ).run(df)

    assert backtest_result.final_equity > 0
    assert len(backtest_result.daily_equity) > 0

    # 3. Calibration from backtest observations. If no trades were created,
    # inject minimal synthetic observations to keep the E2E contract stable.
    observations = CalibrationCollector().collect_from_backtest(backtest_result.to_dict())
    if not observations:
        observations = [
            {
                "ticker": "NVDA",
                "prediction_date": "2024-01-01",
                "horizon": "20d",
                "predicted_probability": 0.7,
                "actual_outcome": 1,
                "realized_return": 0.05,
            },
            {
                "ticker": "NVDA",
                "prediction_date": "2024-01-02",
                "horizon": "20d",
                "predicted_probability": 0.8,
                "actual_outcome": 0,
                "realized_return": -0.03,
            },
        ]
    calibration_table = ProbabilityCalibrator(bin_size=0.2).fit(observations).to_dict()
    calibration_repo = CalibrationRepository()
    calibration_repo.save_calibration_table(calibration_table)

    # 4. Adaptive learning update
    learning_update = AdaptiveLearningEngineV2().update(
        [
            RuleSample("probability", True, 0.06),
            RuleSample("probability", True, 0.04),
            RuleSample("pattern", True, 0.03),
            RuleSample("volume", True, -0.02),
        ]
    ).to_dict()
    learning_repo = LearningV2Repository()
    learning_repo.save_update(learning_update)

    # 5. Calibrated + adaptive pipeline
    calibrated_context = DecisionContext(
        market="us",
        ticker="NVDA",
        market_data=df,
        account_balance=100_000_000,
        cash=50_000_000,
        equity_peak=100_000_000,
        market_regime="BULL",
        vix=18,
    )
    calibrated_result = ADEPipeline(
        calibration_repository=calibration_repo,
        learning_v2_repository=learning_repo,
    ).run(calibrated_context)

    assert calibrated_result.decisions["probability"]["calibration"]["applied"] is True
    assert "candidate" in calibrated_result.decisions
    assert "explanation" in calibrated_result.decisions

    # 6. Unified report
    report = ReportEngine().build_report(
        ticker="NVDA",
        pipeline_result=calibrated_result.to_dict(),
        backtest_result=backtest_result.to_dict(),
        calibration_table=calibration_table,
        learning_update=learning_update,
    )
    markdown = ReportEngine().markdown(report)

    assert report["engine_version"] == "report-engine-v1.0.0"
    assert report["metadata"]["has_pipeline"] is True
    assert report["metadata"]["has_backtest"] is True
    assert report["metadata"]["has_calibration"] is True
    assert report["metadata"]["has_learning"] is True
    assert "ADE Decision Report - NVDA" in markdown

    calibration_repo.close()
    learning_repo.close()
