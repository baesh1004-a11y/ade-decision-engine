# ADE Probability Engine v1.0

## Purpose

The Probability Engine converts Pattern Context evidence into explicit investment probability.

It answers:

```text
What is the probability of upside?
What is the downside probability?
What is the expected return?
What is the expected drawdown proxy?
Is the risk-reward attractive?
```

## Pipeline Position

```text
Pattern Matching
    ↓
Pattern Context
    ↓
Probability Engine
    ↓
Candidate Engine
    ↓
Risk Engine
```

## Inputs

Probability Engine consumes `PatternContextDecision` as a dictionary.

Key fields:

```text
combined_similarity
context_similarity
pattern_similarity
expected_returns.return_20d
win_rates.win_rate_20d
pattern.matches.forward_returns
risk_flags
```

## Output

```json
{
  "engine_version": "probability-engine-v1.0.0",
  "ticker": "NVDA",
  "horizon": "20d",
  "upside_probability": 0.72,
  "downside_probability": 0.28,
  "expected_return": 0.06,
  "expected_mdd": -0.02,
  "risk_reward": 3.0,
  "confidence": 0.80,
  "recommendation": "BUY",
  "risk_flags": [],
  "reasons": []
}
```

## Recommendation Logic

```text
STRONG_BUY
- upside probability >= 70%
- expected return >= 5%
- risk reward >= 2.0
- confidence >= 75%

BUY
- upside probability >= 60%
- expected return > 0
- risk reward >= 1.2
- confidence >= 65%

WATCH
- upside probability >= 52%
- expected return > 0

AVOID
- negative expected return or weak probability evidence
```

## Candidate Integration

Candidate score is adjusted by Probability Engine:

```text
STRONG_BUY → score +15, confidence +0.08
BUY        → score +8,  confidence +0.04
WATCH      → score +3,  confidence +0.01
AVOID      → score -15, confidence -0.08
```

Candidate output adds:

```json
{
  "probability_adjustment": {
    "score_delta": 8,
    "confidence_delta": 0.04,
    "upside_probability": 0.64,
    "expected_return": 0.03,
    "risk_reward": 1.8,
    "probability_confidence": 0.72,
    "recommendation": "BUY"
  }
}
```

## Database

New table:

```text
probability_decisions
```

## Tests

```bash
pytest tests/test_probability_engine.py
pytest tests/test_ade_pipeline.py
```

## v2.0 Expansion

Next improvements:

```text
True MDD calculation from forward paths
Multi-horizon probability curve
Calibration with historical backtest results
Bayesian confidence intervals
Regime-specific probability model
Probability-based position sizing
```
