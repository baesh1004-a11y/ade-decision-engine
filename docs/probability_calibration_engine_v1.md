# ADE Probability Calibration Engine v1

## Purpose

Probability Calibration Engine turns ADE from a prediction system into a self-correcting prediction system.

It compares:

```text
Predicted probability
    ↓
Actual result
    ↓
Observed frequency
    ↓
Calibration table
```

## Implemented Components

```text
calibration/models.py
calibration/collector.py
calibration/calibrator.py
calibration/updater.py
calibration/persistence.py
```

## Flow

```text
Backtest trades
    ↓
CalibrationCollector
    ↓
ProbabilityObservation
    ↓
ProbabilityCalibrator
    ↓
CalibrationTable
    ↓
ProbabilityUpdater
    ↓
Calibrated Probability
```

## Bin-Based Calibration

v1 uses fixed probability bins.

Example:

```text
Predicted 80~90%
Observed 60%
Bias +25%
```

Then future probabilities in that bin can be adjusted toward the observed frequency.

## Example

```python
from calibration.collector import CalibrationCollector
from calibration.calibrator import ProbabilityCalibrator
from calibration.updater import ProbabilityUpdater

observations = CalibrationCollector().collect_from_backtest(backtest_result.to_dict())
table = ProbabilityCalibrator(bin_size=0.1).fit(observations)
updated = ProbabilityUpdater().apply(probability_decision, table.to_dict())
```

## Persistence

Migration:

```text
database/migrations/003_add_probability_calibration.sql
```

Tables:

```text
probability_observations
probability_calibration_tables
```

## Output

`CalibrationTable` includes:

```text
engine_version
horizon
sample_count
bins
global_bias
brier_score
reasons
```

`ProbabilityUpdater` adds:

```json
{
  "raw_upside_probability": 0.85,
  "upside_probability": 0.62,
  "calibration": {
    "applied": true,
    "global_bias": 0.18,
    "brier_score": 0.21
  }
}
```

## Tests

```bash
pytest tests/test_probability_calibration.py
```

## Current Limitations

v1 is simple and transparent:

```text
Fixed bins
No isotonic regression yet
No Platt scaling yet
No Bayesian uncertainty yet
No automatic live pipeline injection yet
```

## Next Step

The next step is to connect the latest calibration table into `ADEPipeline`, so Probability Engine output is automatically calibrated before it adjusts Candidate score.
