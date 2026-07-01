# ADE v1.0 Completion Engines

This document summarizes the final five engines added to complete ADE v1.0.

## 1. Candidate Rule Score Engine

Path:

```text
candidate_rules/engine.py
```

Purpose:

```text
Break a candidate score into explicit rule scores.
```

Output:

```json
{
  "rule_scores": {
    "trend": 20,
    "momentum": 15,
    "volume": 10,
    "pattern": 15,
    "probability": 15,
    "volatility": 10
  },
  "weighted_rule_scores": {},
  "total_score": 85
}
```

This lets Adaptive Learning v2 adjust rules directly.

## 2. Strategy Library

Path:

```text
strategy_library/engine.py
```

Strategies:

```text
breakout
pullback
trend_following
momentum
mean_reversion
swing
```

The engine returns the best matching strategy and all strategy scores.

## 3. Multi-Timeframe Engine

Path:

```text
timeframe/engine.py
```

Purpose:

```text
Evaluate daily, weekly, and optional intraday frame alignment.
```

Output:

```text
ALIGNED
MIXED
WEAK
INSUFFICIENT
```

## 4. Online Learning Orchestrator

Path:

```text
online_learning/orchestrator.py
```

Flow:

```text
Backtest Result
    ↓
Calibration Observations
    ↓
Calibration Table
    ↓
Rule Samples
    ↓
Adaptive Learning Update
    ↓
Repositories
```

## 5. FastAPI Entry Point

Path:

```text
api/main.py
```

Endpoints:

```text
GET  /health
POST /decision
POST /report
```

Run example:

```bash
uvicorn api.main:app --reload
```

## Tests

```bash
pytest tests/test_v1_completion_engines.py
pytest
```

## ADE v1.0 Final Flow

```text
Market Data
    ↓
Indicator Pipeline
    ↓
Pattern Memory
    ↓
Pattern Context
    ↓
Probability
    ↓
Calibration
    ↓
Candidate Rule Scores
    ↓
Strategy Library
    ↓
Multi-Timeframe
    ↓
Risk / Position / Entry / Exit
    ↓
Backtest
    ↓
Online Learning
    ↓
Adaptive Learning v2
    ↓
Explainable AI
    ↓
Report
    ↓
FastAPI
```

## Remaining After v1.0

These are v2+ items:

```text
Bayesian probability
FAISS/Qdrant production vector DB
Dashboard UI
HTML/PDF report rendering
Scheduled jobs
Live broker integration
```
