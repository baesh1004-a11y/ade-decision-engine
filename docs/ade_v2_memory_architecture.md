# ADE v2 Memory Architecture

## Purpose

ADE v2 changes the core pattern architecture from runtime-only matching to memory-first matching.

Before:

```text
Current OHLCV
  ↓
Build historical vectors every run
  ↓
Pattern Matching
  ↓
Pattern Context
  ↓
Probability
```

After:

```text
Historical OHLCV
  ↓
Pattern Memory Builder
  ↓
Pattern Memory Repository
  ↓
Current Pattern Vector
  ↓
Memory Search
  ↓
Pattern Context
  ↓
Probability
```

## New Default Pipeline

```text
Indicator Engine
    ↓
Pattern Memory Auto-Build
    ↓
Memory Pattern Matching
    ↓
Pattern Context Engine
    ↓
Probability Engine
    ↓
Candidate Engine
    ↓
Risk Engine
    ↓
Position Sizing Engine
    ↓
Entry Timing Engine
    ↓
Exit / Portfolio / Learning
```

## Core Files

```text
pattern/repository.py
pattern/memory.py
pattern/memory_matching.py
pattern/context.py
core/pipeline.py
tests/test_ade_pipeline.py
```

## Repository Interface

`pattern/repository.py` defines the backend-agnostic memory repository protocol.

```text
MemoryRepository
    ├── PatternMemoryRepository(SQLite v1.0)
    ├── FAISS backend later
    └── Qdrant backend later
```

## SQLite v1.0 Backend

Current default backend:

```text
PatternMemoryRepository
```

Storage:

```text
SQLite
JSON vector
JSON forward returns
Cosine similarity search
```

## Pipeline Behavior

`ADEPipeline` now accepts:

```python
ADEPipeline(
    memory_repository=None,
    auto_build_memory=True,
    memory_window=20,
    memory_top_k=10,
    horizons=(5, 10, 20, 40),
)
```

If memory is empty and `auto_build_memory=True`, the pipeline builds Pattern Memory from the provided `market_data`.

## Decision Output

The pipeline now includes:

```json
{
  "pattern_memory": {
    "records": 100,
    "backend": "sqlite"
  },
  "pattern": {
    "engine_version": "pattern-memory-matching-v1.0.0"
  },
  "pattern_context": {},
  "probability": {},
  "candidate": {}
}
```

## Why This Matters

This turns ADE from a system that compares everything every time into a system that remembers historical patterns.

This is the first step toward:

```text
Large-scale Pattern Memory
Vector DB
Backtesting
Probability calibration
Adaptive learning
```

## Tests

```bash
pytest tests/test_pattern_memory.py
pytest tests/test_ade_pipeline.py
pytest
```

## Next Step

The next major engine should be Backtesting Engine.

Backtesting will run ADE across historical dates and store:

```text
signal date
candidate score
probability
entry decision
exit result
return
MDD
win/loss
```

This will allow Probability Engine calibration and Adaptive Learning.
