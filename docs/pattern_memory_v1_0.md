# ADE Pattern Memory v1.0

## Purpose

Pattern Memory is the memory layer of ADE.

It stores historical pattern vectors so ADE does not need to recalculate and compare every historical window from scratch each time.

## Why it matters

Before Pattern Memory:

```text
Current chart
  ↓
Build historical vectors every run
  ↓
Compare all windows
```

After Pattern Memory:

```text
Historical chart windows
  ↓
Pattern vectors stored in memory DB
  ↓
Current vector searches memory
  ↓
Top-K similar historical patterns
```

## v1.0 Scope

v1.0 uses:

```text
SQLite
JSON vector storage
Cosine similarity
Brute-force local search
```

This is intentionally simple and testable. FAISS/Qdrant can replace the search backend in v2.0 without changing the high-level interface.

## Core Files

```text
pattern/memory.py
pattern/memory_matching.py
tests/test_pattern_memory.py
database/migrations/001_add_pattern_memory.sql
```

## Main Classes

```text
PatternMemoryRecord
PatternMemoryRepository
PatternMemoryBuilder
PatternMemoryMatchingEngine
```

## Build Memory

```python
from pattern.memory import PatternMemoryRepository, build_pattern_memory

repo = PatternMemoryRepository("ade.db")
count = build_pattern_memory(
    df,
    market="us",
    ticker="NVDA",
    repository=repo,
    window=20,
    horizons=(5, 10, 20, 40),
)
```

## Search Memory

```python
from pattern.memory_matching import PatternMemoryMatchingEngine

engine = PatternMemoryMatchingEngine(repo, window=20, top_k=10)
decision = engine.evaluate(df, market="us", ticker="NVDA")
print(decision.to_dict())
```

## Output

```json
{
  "engine_version": "pattern-memory-matching-v1.0.0",
  "ticker": "NVDA",
  "window": 20,
  "top_k": 10,
  "match_count": 10,
  "avg_similarity": 0.82,
  "expected_returns": {
    "return_20d": 0.04
  },
  "win_rates": {
    "win_rate_20d": 0.7
  },
  "risk_flags": [],
  "matches": []
}
```

## Database

New migration:

```text
database/migrations/001_add_pattern_memory.sql
```

Table:

```text
pattern_memory
```

## Tests

```bash
pytest tests/test_pattern_memory.py
```

## v2.0 Direction

Pattern Memory v2.0 should add:

```text
FAISS or Qdrant backend
Approximate nearest neighbor search
Cross-market memory
Sector-aware memory
Regime-aware memory partitioning
Memory refresh jobs
Memory quality metrics
```
