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
core/pipeline.py
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
CalibrationRepository
    ↓
ADEPipeline
    ↓
ProbabilityUpdater
    ↓
Calibrated Probability
    ↓
Candidate Score
```

## Pipeline Integration

`ADEPipeline` now accepts:

```python
ADEPipeline(
    calibration_repository=repo,
    use_calibration=True,
)
```

When a latest calibration table exists for the Probability horizon, the pipeline applies it before Candidate scoring.

```text
Pattern Context
    ↓
Probability Engine
    ↓
Latest Calibration Table
    ↓
Probability Updater
    ↓
Candidate Engine
```

If no calibration repository or table exists, the pipeline continues safely and marks:

```json
{
  "calibration": {
    "applied": false,
    "reason": "No calibration table available"
  }
}
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
from calibration.persistence import CalibrationRepository
from core.pipeline import ADEPipeline

observations = CalibrationCollector().collect_from_backtest(backtest_result.to_dict())
table = ProbabilityCalibrator(bin_size=0.1).fit(observations)
repo = CalibrationRepository("ade.db")
repo.save_calibration_table(table)

pipeline = ADEPipeline(calibration_repository=repo)
result = pipeline.run(context)
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

Candidate output adds:

```json
{
  "probability_adjustment": {
    "upside_probability": 0.62,
    "raw_upside_probability": 0.85,
    "calibration_applied": true
  }
}
```

## Tests

```bash
pytest tests/test_probability_calibration.py
pytest tests/test_ade_pipeline.py
```

## Current Limitations

v1 is simple and transparent:

```text
Fixed bins
No isotonic regression yet
No Platt scaling yet
No Bayesian uncertainty yet
Calibration table must be generated from backtest results first
```

## Next Step

The next step is Explainable AI Engine.

It will transform ADE decisions into human-readable explanations:

```text
Why BUY?
Why WATCH?
Why AVOID?
What evidence changed after calibration?
```
