# 07. Risk Engine

## Purpose

Risk Engine은 Signal Engine의 후보가 계좌 정책상 허용 가능한지 판단한다. 신호가 좋아도 리스크 조건을 통과하지 못하면 후보는 거절된다.

## Responsibility Boundary

- Signal Engine: 후보 생성
- Portfolio State Engine: 계좌 상태 제공
- Risk Engine: 위험 한도와 허용 금액 판단
- Decision Engine: 최종 행동 결정
- Order Engine: 실행 요청 생성 인터페이스

## Inputs

```python
RiskInput(
    symbol="005930",
    signal_score=72.5,
    requested_amount=3_000_000,
    cash=5_000_000,
    total_equity=20_000_000,
    total_market_value=10_000_000,
    current_position_value=0,
    today_pnl_pct=-0.005,
    volatility_pct=0.03,
    avg_volume_value=50_000_000_000,
    policy=RiskPolicy(),
)
```

## Outputs

```python
RiskResult(
    approved=True,
    risk_score=22.4,
    max_allowed_amount=2_500_000,
    adjusted_amount=2_500_000,
    hard_blocks=[],
    warnings=["REQUESTED_AMOUNT_REDUCED"],
)
```

## Policy Defaults

| Policy | Default | Meaning |
|---|---:|---|
| max_position_pct | 10% | max single position |
| max_total_exposure_pct | 90% | max invested ratio |
| max_daily_loss_pct | 2% | daily loss limit |
| min_cash_buffer_pct | 10% | minimum cash buffer |
| max_volatility_pct | 8% | volatility cap |
| min_avg_volume_value | 1,000,000,000 | liquidity floor |
| max_risk_score | 70 | risk score cap |

## Hard Block Rules

- insufficient cash after buffer
- daily loss limit exceeded
- position limit exceeded
- total exposure limit exceeded
- liquidity too low
- volatility too high
- risk score too high

## Amount Limit Formula

```python
max_position_value = total_equity * max_position_pct
remaining_position_capacity = max_position_value - current_position_value
max_total_exposure = total_equity * max_total_exposure_pct
exposure_capacity = max_total_exposure - total_market_value
max_allowed_amount = min(requested_amount, cash_available, remaining_position_capacity, exposure_capacity)
```

## Risk Score

```python
risk_score = (
    position_risk * 0.30
    + exposure_risk * 0.25
    + volatility_risk * 0.20
    + liquidity_risk * 0.15
    + drawdown_risk * 0.10
)
```

## Test Plan

- normal case is approved
- daily loss limit returns rejected result
- position limit reduces amount
- low liquidity returns rejected result
- high volatility returns rejected result
- total exposure cap returns rejected result
