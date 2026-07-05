# 08. Decision Engine Core

## Purpose

Decision Engine Core는 ADE의 핵심 판단 계층이다. Signal, Risk, Portfolio State를 통합하여 최종 행동을 결정한다.

## Decision Values

| Decision | Meaning |
|---|---|
| BUY | 신규 또는 추가 매수 후보 승인 |
| HOLD | 보유 유지 또는 관망 |
| REDUCE | 일부 축소 |
| SELL | 전량 청산 후보 |
| REJECT | 신호는 있으나 리스크 조건 미충족 |
| NO_ACTION | 의미 있는 행동 없음 |

## Inputs

```python
DecisionInput(
    symbol="005930",
    signal_score=75,
    signal_action="BUY_CANDIDATE",
    risk_approved=True,
    risk_score=22,
    risk_adjusted_amount=2_500_000,
    risk_hard_blocks=[],
    has_position=False,
    position_weight=0.0,
    position_pnl_pct=0.0,
    current_price=70000,
)
```

## Output

```python
DecisionResult(
    symbol="005930",
    decision="BUY",
    confidence=0.78,
    order_side="BUY",
    order_amount=2_500_000,
    order_quantity=35,
    reasons=["Buy candidate signal", "Risk approved"],
)
```

## Architecture

```text
Signal Engine
  ↓
Risk Engine
  ↓
Portfolio State
  ↓
Decision Engine Core
  ├─ Signal Gate
  ├─ Risk Gate
  ├─ Position Gate
  ├─ Sell Rule
  ├─ Buy Rule
  └─ Explain Rule
  ↓
DecisionResult
  ↓
Order Engine
```

## Policy

| Policy | Default |
|---|---:|
| strong_buy_threshold | 80 |
| buy_threshold | 65 |
| watch_threshold | 50 |
| sell_threshold | 35 |
| stop_loss_pct | -7% |
| reduce_loss_pct | -4% |
| take_profit_pct | 12% |
| min_confidence_to_buy | 0.65 |
| max_position_weight | 10% |

## Rule Priority

1. Existing position exit/reduce rules
2. Risk rejection
3. Strong buy rule
4. Buy candidate rule
5. Hold rule
6. No action rule

## Confidence Formula

```python
confidence = (
    signal_quality * 0.50
    + risk_quality * 0.30
    + portfolio_fit * 0.20
)

signal_quality = signal_score / 100
risk_quality = 1 - risk_score / 100
portfolio_fit = 1 - current_position_weight / max_position_weight
```

## Database

### decision_runs

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | run id |
| run_id | TEXT | batch id |
| started_at | DATETIME | start time |
| finished_at | DATETIME | finish time |
| universe_size | INTEGER | evaluated symbols |
| decisions_count | INTEGER | generated decisions |
| status | TEXT | SUCCESS/FAILED |

### decisions

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | decision id |
| run_id | TEXT | batch id |
| symbol | TEXT | stock code |
| signal_score | REAL | signal score |
| risk_score | REAL | risk score |
| confidence | REAL | confidence |
| decision | TEXT | BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION |
| order_side | TEXT | BUY/SELL/NONE |
| order_amount | INTEGER | amount |
| order_quantity | INTEGER | quantity |
| reasons | JSON | explanation |
| created_at | DATETIME | created time |

## Test Plan

- strong signal and approved risk returns BUY
- candidate signal with enough confidence returns BUY
- rejected risk returns REJECT
- watch score returns HOLD
- weak score without position returns NO_ACTION
- stop-loss condition returns SELL
- reduced loss condition with weak signal returns REDUCE
- take-profit condition with weakening signal returns REDUCE
- price zero returns quantity zero
