# ADE Pattern Matching Engine v1.0

## Purpose

The Pattern Matching Engine is the first core AI layer of ADE.

It answers:

> Has the current chart appeared before, and what happened after similar patterns?

## Scope of v1.0

v1.0 is intentionally simple and executable without external infrastructure.

It supports:

- OHLCV window vectorization.
- Cosine similarity search.
- Historical top-k pattern matching.
- Forward return statistics.
- Win-rate calculation.
- Risk flags for weak evidence.

## Pipeline

```text
Current OHLCV Window
      ↓
PatternVectorizer
      ↓
Normalized Vector
      ↓
Historical Window Vectors
      ↓
Cosine Similarity
      ↓
Top-K Similar Patterns
      ↓
Forward Return Statistics
```

## Vector Design

Each window is transformed into six normalized feature groups:

```text
1. Close path
2. Candle body
3. Candle range
4. Upper wick
5. Lower wick
6. Volume pattern
```

For window size 20:

```text
20 bars × 6 feature groups = 120-dimensional vector
```

## Example

```python
from pattern.matching import PatternMatchingEngine

engine = PatternMatchingEngine(window=20, top_k=10, horizons=(5, 10, 20, 40))
decision = engine.evaluate(df, ticker="NVDA")
print(decision.to_dict())
```

## Output

```json
{
  "engine_version": "pattern-matching-v1.0.0",
  "ticker": "NVDA",
  "window": 20,
  "top_k": 10,
  "match_count": 10,
  "avg_similarity": 0.84,
  "expected_returns": {
    "return_5d": 0.012,
    "return_10d": 0.021,
    "return_20d": 0.038,
    "return_40d": 0.061
  },
  "win_rates": {
    "win_rate_5d": 0.6,
    "win_rate_10d": 0.7,
    "win_rate_20d": 0.7,
    "win_rate_40d": 0.8
  },
  "risk_flags": [],
  "matches": []
}
```

## Risk Flags

The engine flags weak evidence when:

```text
Insufficient similar samples
Low pattern similarity
Negative 20-day expected return
```

## Database

New tables:

```text
pattern_vectors
pattern_match_decisions
```

## Tests

```bash
pytest tests/test_pattern_matching_engine.py
```

Covered cases:

- Fixed-length vector generation.
- Backward-compatible vector helper.
- Top-k historical matching.
- Forward return calculation.
- Similarity sorting.
- Dict output helper.
- Missing columns.
- Insufficient rows.

## Current Limitation

v1.0 uses brute-force in-memory similarity search.

This is fine for local tests and small history, but for large-scale use the next step is:

```text
Vector DB / ANN index
```

## v2.0 Expansion

Pattern Matching Engine v2.0 should add:

- Vector DB storage.
- Approximate nearest neighbor search.
- Cross-ticker similarity.
- Regime-aware matching.
- Sector-aware matching.
- Volatility-normalized matching.
- Integration into Candidate Engine scoring.
