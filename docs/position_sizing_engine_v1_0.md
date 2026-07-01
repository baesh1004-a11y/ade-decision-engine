# ADE Engine #2: Position Sizing Engine v1.0

## Purpose

The Position Sizing Engine answers the second ADE question after candidate selection:

> How much should the system buy?

It converts a Candidate Decision Engine output into an executable position size using account balance, available cash, confidence, market regime, volatility, stop-loss distance, sector exposure, and portfolio heat.

## Input

```python
PositionSizingInput(
    ticker="NVDA",
    price=100.0,
    grade="A",
    confidence=0.92,
    risk_level="LOW",
    atr=2.0,
    stop_loss_price=None,
    market_regime="BULL",
    account=AccountState(
        account_balance=100_000_000,
        cash=100_000_000,
        sector_exposure=0.0,
        portfolio_heat=0.0,
    ),
)
```

## Output

```json
{
  "engine_version": "position-sizing-v1.0.0",
  "ticker": "NVDA",
  "recommended_weight": 0.126,
  "buy_amount": 12600000.0,
  "shares": 126000,
  "max_loss": 0.0,
  "risk_score": 15,
  "kelly_weight": 0.0,
  "atr_risk": 0.02,
  "sector_adjustment": 1.0,
  "heat_adjustment": 1.0,
  "cash_limited": false,
  "reasons": [
    "Base weight from grade A: 10.00%"
  ]
}
```

## Core Formula

```text
final_weight = base_weight
             * confidence_multiplier
             * market_multiplier
             * risk_multiplier
             * atr_multiplier
             * sector_adjustment
             * heat_adjustment
```

The result is then capped by:

```text
max_position_weight
Kelly weight
stop-loss / ATR risk budget
available cash
```

## Base Weights

| Grade | Base Weight |
|---|---:|
| S | 15% |
| A | 10% |
| B | 6% |
| C | 3% |
| D | 1% |
| F | 0% |

## Confidence Multiplier

| Confidence | Multiplier |
|---:|---:|
| >= 0.90 | 1.20 |
| >= 0.80 | 1.10 |
| >= 0.70 | 1.00 |
| >= 0.60 | 0.80 |
| < 0.60 | 0.50 |

## Market Regime Multiplier

| Regime | Multiplier |
|---|---:|
| BULL | 1.00 |
| SIDEWAY | 0.80 |
| BEAR | 0.50 |

## Risk Controls

1. **ATR Risk Adjustment**
   - ATR / Price >= 8%: 0.50x
   - ATR / Price >= 5%: 0.70x
   - ATR / Price >= 3%: 0.90x
   - ATR / Price < 3%: 1.05x

2. **Stop-loss / ATR Risk Budget**
   - Default max trade risk: 1% of account balance.
   - If `stop_loss_price` exists, risk per share is `price - stop_loss_price`.
   - If stop is absent but ATR exists, risk per share is `2 * ATR`.

3. **Sector Exposure**
   - Default max sector exposure: 30%.
   - If exposure exceeds this level, new allocation is blocked.

4. **Portfolio Heat**
   - Default max portfolio heat: 6%.
   - If portfolio heat exceeds this level, new allocation is blocked.

## Test Plan

```bash
pytest tests/test_position_sizing.py
```

Covered cases:

- A-grade high-confidence bull-market recommendation.
- Bear-market size reduction.
- High ATR volatility reduction.
- Sector exposure blocking.
- Stop-loss risk budget cap.
- Dict payload backward compatibility.
- Invalid input validation.

## Next Engine

The next recommended engine is the Entry Timing Engine. It should decide:

> When and at what price should the system enter?
