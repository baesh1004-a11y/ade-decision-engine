from calibration.calibrator import ProbabilityCalibrator
from calibration.collector import CalibrationCollector
from calibration.models import ProbabilityObservation
from calibration.persistence import CalibrationRepository
from calibration.updater import ProbabilityUpdater


def _observations():
    return [
        ProbabilityObservation("NVDA", "2024-01-01", "20d", 0.85, 1, realized_return=0.10),
        ProbabilityObservation("NVDA", "2024-01-02", "20d", 0.82, 0, realized_return=-0.04),
        ProbabilityObservation("NVDA", "2024-01-03", "20d", 0.75, 1, realized_return=0.06),
        ProbabilityObservation("NVDA", "2024-01-04", "20d", 0.65, 1, realized_return=0.03),
        ProbabilityObservation("NVDA", "2024-01-05", "20d", 0.35, 0, realized_return=-0.02),
    ]


def test_calibrator_builds_bins_and_bias():
    table = ProbabilityCalibrator(bin_size=0.2).fit(_observations(), horizon="20d")

    assert table.engine_version == "probability-calibration-v1.0.0"
    assert table.sample_count == 5
    assert len(table.bins) > 0
    assert table.brier_score >= 0


def test_updater_applies_calibrated_probability():
    table = ProbabilityCalibrator(bin_size=0.2).fit(_observations(), horizon="20d").to_dict()
    probability = {
        "upside_probability": 0.85,
        "expected_return": 0.06,
        "risk_reward": 2.0,
        "confidence": 0.8,
        "recommendation": "STRONG_BUY",
        "reasons": [],
    }

    updated = ProbabilityUpdater().apply(probability, table)

    assert updated["raw_upside_probability"] == 0.85
    assert updated["calibration"]["applied"] is True
    assert 0 <= updated["upside_probability"] <= 1


def test_collector_extracts_observations_from_backtest_result():
    result = {
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
                            "recommendation": "BUY",
                        }
                    }
                },
            }
        ],
    }

    observations = CalibrationCollector().collect_from_backtest(result)

    assert len(observations) == 1
    assert observations[0].actual_outcome == 1
    assert observations[0].predicted_probability == 0.7


def test_calibration_repository_saves_observations_and_table():
    repo = CalibrationRepository()
    observations = _observations()
    count = repo.save_observations(observations)
    table = ProbabilityCalibrator(bin_size=0.2).fit(observations).to_dict()
    table_id = repo.save_calibration_table(table)
    latest = repo.fetch_latest_calibration_table("20d")

    assert count == 5
    assert table_id > 0
    assert latest is not None
    assert latest["engine_version"] == "probability-calibration-v1.0.0"
    assert len(repo.fetch_observations("20d")) == 5
    repo.close()


def test_calibrator_requires_observations():
    try:
        ProbabilityCalibrator().fit([])
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
