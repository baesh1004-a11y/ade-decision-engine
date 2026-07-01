# ADE Report Engine v1

## Purpose

Report Engine combines ADE outputs into a single human-readable report.

It answers:

```text
What did ADE decide?
Why did it decide that?
How did it perform in backtests?
Was probability calibrated?
Which rules are being weighted higher or lower?
```

## Implemented Components

```text
report/models.py
report/builder.py
report/renderer.py
report/engine.py
tests/test_report_engine.py
```

## Inputs

Report Engine can combine:

```text
Pipeline Result
Backtest Result
Calibration Table
Adaptive Learning Update
Explainable AI Output
```

## Flow

```text
ADEPipeline
BacktestSimulator
ProbabilityCalibrator
AdaptiveLearningEngineV2
ExplainableAIEngine
        ↓
ReportEngine
        ↓
ADEReport
        ↓
Markdown / JSON
```

## Example

```python
from report.engine import ReportEngine

engine = ReportEngine()
report = engine.build_report(
    ticker="NVDA",
    pipeline_result=pipeline_result.to_dict(),
    backtest_result=backtest_result.to_dict(),
    calibration_table=calibration_table.to_dict(),
    learning_update=learning_update.to_dict(),
)

markdown = engine.markdown(report)
json_text = engine.json(report)
```

## Sections

Generated sections include:

```text
Decision Summary
Probability & Calibration
Risk & Position
Explainable AI
Backtest Performance
Probability Calibration
Adaptive Learning v2
```

## Output

```json
{
  "engine_version": "report-engine-v1.0.0",
  "title": "ADE Decision Report - NVDA",
  "ticker": "NVDA",
  "summary": "NVDA의 최종 판단은 WATCHLIST이며...",
  "sections": [],
  "metadata": {
    "section_count": 7,
    "has_pipeline": true,
    "has_backtest": true,
    "has_calibration": true,
    "has_learning": true
  }
}
```

## Tests

```bash
pytest tests/test_report_engine.py
```

## Current Limitations

v1 is Markdown/JSON only.

```text
No HTML template yet
No PDF generation yet
No charts yet
No dashboard integration yet
```

## Next Step

System stabilization:

```text
Run full pytest
Fix integration bugs
Normalize DB schemas
Add CLI or FastAPI endpoint
```
