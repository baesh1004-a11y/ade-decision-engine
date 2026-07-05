# 05. Portfolio State Engine

## Purpose

Portfolio State Engine은 현금, 보유종목, 평가금액, 평가손익, 비중, 미체결 주문을 하나의 표준 계좌 상태로 통합한다.

## Inputs

- cash balance
- positions
- current prices
- open orders
- account metadata

## Outputs

```python
PortfolioState(
    cash=5_000_000,
    total_market_value=15_000_000,
    total_equity=20_000_000,
    positions=[...],
    open_orders=[...]
)
```

## Architecture

```text
Broker Adapter
  ↓
load_cash / load_positions / load_open_orders
  ↓
mark_to_market()
  ↓
calculate_weights()
  ↓
PortfolioState
  ↓
Risk Engine / Decision Engine
```

## Database

### portfolio_snapshots

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | snapshot id |
| captured_at | DATETIME | captured time |
| cash | INTEGER | cash balance |
| total_market_value | INTEGER | total value of positions |
| total_equity | INTEGER | cash + market value |
| total_pnl | INTEGER | unrealized pnl |
| risk_exposure | REAL | invested ratio |

### positions

| Column | Type | Description |
|---|---|---|
| symbol | TEXT | stock code |
| quantity | INTEGER | holding quantity |
| avg_price | REAL | average entry price |
| current_price | REAL | latest price |
| market_value | REAL | quantity * current price |
| unrealized_pnl | REAL | unrealized pnl |
| weight | REAL | market value / total equity |

## Core Formula

```python
total_market_value = sum(p.quantity * p.current_price for p in positions)
total_equity = cash + total_market_value
position.weight = position.market_value / total_equity
risk_exposure = total_market_value / total_equity
```
