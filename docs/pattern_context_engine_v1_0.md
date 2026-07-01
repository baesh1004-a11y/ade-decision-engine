# ADE Pattern Context Engine v1.0

## Purpose

Pattern Matching Engine compares chart shapes.

Pattern Context Engine compares:

```text
Chart Pattern + Market Context
```

It answers:

> Is the current chart similar to past charts under a similar market environment?

## Inputs

```python
PatternContextEngine().evaluate(
    df,
    ticker="NVDA",
    market_regime="BULL",
    vix=18,
)
```

## Context Factors

v1.0 uses only currently available data:

```text
Market Regime
Trend Score
Volume Score
Volatility Score
VIX Score
```

## Output

```json
{
  "engine_version": "pattern-context-v1.0.0",
  "ticker": "NVDA",
  "pattern_similarity": 0.84,
  "context_similarity": 0.79,
  "combined_similarity": 0.825,
  "expected_returns": {
    "return_20d": 0.031
  },
  "win_rates": {
    "win_rate_20d": 0.7
  },
  "risk_flags": [],
  "current_context": {},
  "pattern": {}
}
```

## Candidate Integration

The integrated ADE Pipeline now runs:

```text
Indicator
  ↓
Pattern Context
  ↓
Candidate
  ↓
Risk
  ↓
Position
  ↓
Entry
```

Candidate score is conservatively adjusted:

```text
Strong pattern-context evidence
→ score +12, confidence +0.06

Supportive pattern-context evidence
→ score +6, confidence +0.03

Negative expected return
→ score -12, confidence -0.06

Weak context similarity
→ score -6, confidence -0.03
```

## Database

New table:

```text
pattern_context_decisions
```

## Tests

```bash
pytest tests/test_pattern_context_engine.py
pytest tests/test_ade_pipeline.py
```

## v2.0 Expansion

Next improvements:

```text
Sector strength
Interest rate regime
Index trend context
Cross-asset context
Macro event filters
Regime-specific similarity weights
```
