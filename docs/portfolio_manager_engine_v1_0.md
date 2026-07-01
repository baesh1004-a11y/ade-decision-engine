# ADE Engine #5: Portfolio Manager Engine v1.0

## Purpose

The Portfolio Manager Engine answers the account-level ADE question:

> Is the total account allocation healthy, and what should be rebalanced?

Candidate, Position, Entry, and Exit engines make single-symbol decisions. Portfolio Manager evaluates the whole account across positions, sectors, markets, and cash.

## Scope of v1.0

v1.0 supports:

- Maximum number of positions.
- Maximum single-position weight.
- Maximum sector weight.
- Maximum market/country weight.
- Market-regime cash targets.
- Rebalance recommendations.

## Input

```python
PortfolioState(
    account_balance=100_000_000,
    cash=20_000_000,
    market_regime="SIDEWAY",
    holdings=[
        Holding("NVDA", "US", "SEMICONDUCTOR", 10, 1_000_000),
        Holding("005930", "KR", "SEMICONDUCTOR", 100, 70_000),
    ],
)
```

## Output

```json
{
  "engine_version": "portfolio-manager-v1.0.0",
  "portfolio_score": 88,
  "action": "HOLD",
  "total_value": 100000000.0,
  "cash_weight": 0.20,
  "target_cash_weight": 0.20,
  "position_count": 2,
  "risk_flags": [],
  "recommendations": [],
  "sector_weights": {
    "SEMICONDUCTOR": 0.17
  },
  "market_weights": {
    "US": 0.10,
    "KR": 0.07
  }
}
```

## Actions

| Action | Meaning |
|---|---|
| HOLD | Portfolio is within configured limits. |
| MONITOR | No immediate rebalance, but quality is moderate. |
| REBALANCE | Portfolio needs allocation adjustment. |

## Key Rules

### 1. Position Count

Default max positions: 10.

### 2. Single Position Limit

Default max single-position weight: 20%.

If a position exceeds the limit, the engine recommends `TRIM`.

### 3. Sector Limit

Default max sector weight: 30%.

### 4. Market Limit

Default max market/country weight: 70%.

### 5. Cash Target by Market Regime

| Regime | Target Cash |
|---|---:|
| BULL | 10% |
| SIDEWAY | 20% |
| BEAR | 50% |

### 6. Rebalance Recommendations

The engine can recommend:

- `TRIM`
- `RAISE_CASH`
- `DEPLOY_CASH`

## Database

`portfolio_decisions` stores account-level portfolio decisions.

## Tests

```bash
pytest tests/test_portfolio_engine.py
```

Covered cases:

- Balanced portfolio hold.
- Single-position overweight trim.
- Bear-market cash raising.
- Bull-market excessive cash deployment.
- Sector overweight.
- Too many positions.
- Dict payload compatibility.
- Invalid account balance.
- Invalid holding price.

## v2.0 Expansion

Portfolio Manager v2.0 should add:

- Correlation clustering.
- Factor exposure analysis.
- Volatility contribution per holding.
- Rebalance optimizer.
- Tax-aware trimming.
- Integration with Risk Engine forced deleveraging.
