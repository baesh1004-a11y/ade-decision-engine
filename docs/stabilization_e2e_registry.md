# ADE Stabilization: E2E Test + Engine Registry

## Purpose

This stabilization step improves ADE integration reliability.

It focuses on:

```text
End-to-end verification
Engine dependency injection
Candidate score traceability
Pipeline maintainability
```

## Added Components

```text
core/registry.py
tests/test_e2e_ade_flow.py
```

## Engine Registry

`EngineRegistry` centralizes pipeline dependencies.

Before:

```text
ADEPipeline directly creates every engine
```

After:

```text
EngineRegistry
    ↓
ADEPipeline
```

Benefits:

```text
Easier testing
Cleaner dependency injection
Future FastAPI / CLI integration
Reduced constructor complexity
```

## Pipeline Constructor

`ADEPipeline` now accepts:

```python
ADEPipeline(
    registry=registry,
    calibration_repository=calibration_repo,
    learning_v2_repository=learning_repo,
)
```

If no registry is provided, `build_default_registry()` is used.

## Candidate Score Trace

Candidate now includes `score_trace`.

Example:

```json
{
  "score_trace": {
    "raw_score": 62,
    "probability_base_score": 62,
    "probability_score_delta": 8,
    "probability_score": 70,
    "adaptive_base_score": 70,
    "adaptive_avg_weight": 1.12,
    "adaptive_score": 78
  }
}
```

This makes score changes auditable.

## E2E Test

New test:

```text
tests/test_e2e_ade_flow.py
```

It verifies:

```text
Pipeline
    ↓
Backtest
    ↓
Calibration
    ↓
Adaptive Learning
    ↓
Calibrated + Adaptive Pipeline
    ↓
Report
```

Run:

```bash
pytest tests/test_e2e_ade_flow.py
pytest
```

## Remaining Stabilization Work

```text
Full pytest execution in local/dev CI
Candidate rule-score decomposition
DB schema normalization
CI workflow with pytest
FastAPI or CLI entrypoint
```
