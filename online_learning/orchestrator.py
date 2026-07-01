from __future__ import annotations

from typing import Any

from calibration.calibrator import ProbabilityCalibrator
from calibration.collector import CalibrationCollector
from calibration.persistence import CalibrationRepository
from learning_v2.engine import AdaptiveLearningEngineV2
from learning_v2.models import RuleSample
from learning_v2.persistence import LearningV2Repository


class OnlineLearningOrchestrator:
    """Run calibration and adaptive learning updates as one daily job."""

    def __init__(
        self,
        calibration_repository: CalibrationRepository,
        learning_repository: LearningV2Repository,
    ) -> None:
        self.calibration_repository = calibration_repository
        self.learning_repository = learning_repository
        self.collector = CalibrationCollector()
        self.calibrator = ProbabilityCalibrator()
        self.learning_engine = AdaptiveLearningEngineV2()

    def run_daily_update(
        self,
        backtest_result: dict[str, Any],
        rule_samples: list[RuleSample | dict] | None = None,
        horizon: str = "20d",
    ) -> dict[str, Any]:
        observations = self.collector.collect_from_backtest(backtest_result, horizon=horizon)
        calibration_table = None
        calibration_id = None
        if observations:
            self.calibration_repository.save_observations(observations)
            calibration_table = self.calibrator.fit(observations, horizon=horizon).to_dict()
            calibration_id = self.calibration_repository.save_calibration_table(calibration_table)

        learning_update = None
        learning_id = None
        if rule_samples:
            learning_update = self.learning_engine.update(rule_samples).to_dict()
            learning_id = self.learning_repository.save_update(learning_update)

        return {
            "engine_version": "online-learning-v1.0.0",
            "observation_count": len(observations),
            "calibration_id": calibration_id,
            "learning_id": learning_id,
            "calibration_table": calibration_table,
            "learning_update": learning_update,
            "status": "UPDATED" if calibration_id or learning_id else "NO_NEW_SAMPLES",
        }
