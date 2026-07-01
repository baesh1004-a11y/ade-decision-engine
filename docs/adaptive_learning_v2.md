# ADE Adaptive Learning v2

## Purpose

Adaptive Learning v2 turns ADE from a fixed-rule decision engine into an adaptive decision engine.

It answers:

```text
Which rules worked?
Which rules failed?
Which rules should receive higher or lower weights?
```

## Implemented Components

```text
learning_v2/models.py
learning_v2/evaluator.py
learning_v2/optimizer.py
learning_v2/engine.py
learning_v2/persistence.py
core/pipeline.py
database/migrations/004_add_adaptive_learning_v2.sql
```

## Flow

```text
Backtest / Trade Results
    ↓
RuleSample
    ↓
RuleEvaluator
    ↓
RuleStatistics
    ↓
RuleWeightOptimizer
    ↓
RuleWeight
    ↓
LearningV2Repository
    ↓
ADEPipeline
    ↓
Candidate Score Adjustment
```

## Rule Statistics

Each rule is evaluated by:

```text
sample_count
win_rate
avg_return
avg_win
avg_loss
profit_factor
expectancy
performance_score
```

## Rule Weight

The optimizer converts performance score into bounded weights.

```text
min_weight = 0.5
base_weight = 1.0
max_weight = 1.5
```

Example:

```json
{
  "rule_name": "probability",
  "previous_weight": 1.0,
  "weight": 1.18,
  "reason": "Rule probability weight increased..."
}
```

## Pipeline Integration

`ADEPipeline` accepts:

```python
ADEPipeline(
    learning_v2_repository=repo,
    use_adaptive_weights=True,
)
```

If latest rule weights exist, Candidate score is adjusted:

```text
Candidate Base Score
    ↓
Applicable Rule Weights
    ↓
Average Weight
    ↓
Adjusted Candidate Score
```

Candidate output adds:

```json
{
  "adaptive_learning": {
    "applied": true,
    "base_score": 70,
    "adjusted_score": 82,
    "avg_weight": 1.17,
    "weights": {
      "probability": 1.22,
      "pattern": 1.12
    }
  }
}
```

## Persistence

Migration:

```text
database/migrations/004_add_adaptive_learning_v2.sql
```

Tables:

```text
rule_statistics_v2
rule_weights_v2
learning_updates_v2
```

## Tests

```bash
pytest tests/test_adaptive_learning_v2.py
pytest tests/test_ade_pipeline.py
```

## Current Limitations

v2.0 is transparent and conservative:

```text
Rule matching is reason-string based
Candidate Engine internals are not fully decomposed into rule components yet
No online scheduled retraining yet
No Bayesian uncertainty penalty yet
```

## Next Step

Report Engine.

The report engine should combine:

```text
Backtest summary
Calibration summary
Adaptive learning weights
Explainable AI narrative
```

into Markdown/HTML/PDF-ready outputs.
