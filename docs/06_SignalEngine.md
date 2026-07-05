# 06. Signal Engine

## Purpose

Signal Engine은 시장 데이터에서 종목별 매수 후보 신호를 생성한다. 이 엔진은 주문하거나 리스크 한도를 판단하지 않는다.

## Inputs

- price bars
- indicators
- volume data
- volatility metrics
- optional portfolio state

## Output

```python
Signal(
    symbol="005930",
    score=72.5,
    action="BUY_CANDIDATE",
    trend_score=80,
    momentum_score=70,
    volume_score=65,
    volatility_score=75,
    portfolio_score=60,
)
```

## Architecture

```text
DataHub / Indicators
  ↓
Trend Signal
Momentum Signal
Volume Signal
Volatility Signal
Portfolio Filter
  ↓
SignalScore
  ↓
Risk Engine
```

## Score Formula

```python
signal_score = (
    trend_score * 0.30
    + momentum_score * 0.25
    + volume_score * 0.20
    + volatility_score * 0.15
    + portfolio_score * 0.10
)
```

## Classification

| Score | Action |
|---:|---|
| >= 80 | STRONG_BUY |
| 65-79 | BUY_CANDIDATE |
| 50-64 | WATCH |
| < 50 | IGNORE |

## Database

| Table | Purpose |
|---|---|
| signal_runs | signal execution history |
| signals | final signal by symbol |
| signal_components | component scores |

## Test Plan

- rising trend produces high trend score
- volume surge increases volume score
- overheated momentum is penalized
- excessive volatility is penalized
- insufficient history returns IGNORE
- boundary scores classify correctly at 80, 65, and 50
