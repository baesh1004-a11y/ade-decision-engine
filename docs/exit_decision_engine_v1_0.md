# ADE Engine #4: Exit Decision Engine v1.0

## Purpose

The Exit Decision Engine answers the fourth ADE question:

> When, how much, and why should the system sell?

It converts open-position state and daily market data into a transparent sell recommendation.

## Scope of v1.0

v1.0 uses daily OHLCV and daily indicators only. It supports:

- Partial profit taking.
- Hard stop loss.
- ATR stop.
- ATR trailing stop.
- Trend breakdown exits.
- MACD dead cross.
- RSI overheated / weak-state exits.
- Time exit.
- Gap-down risk handling.
- Candidate deterioration.

## Input

```python
ExitDecisionEngine().evaluate(
    df=enriched_daily_dataframe,
    position=PositionState(
        ticker="NVDA",
        entry_price=100.0,
        shares=100,
        current_price=112.0,
        highest_price=115.0,
        holding_days=15,
        stop_loss_price=95.0,
    ),
    candidate={
        "score": 70,
        "risk_level": "MEDIUM",
    },
)
```

## Output

```json
{
  "engine_version": "exit-decision-v1.0.0",
  "ticker": "NVDA",
  "sell_score": 45,
  "action": "SELL_25",
  "sell_ratio": 0.25,
  "sell_shares": 25,
  "remaining_shares": 75,
  "current_price": 112.0,
  "pnl_pct": 0.12,
  "risk_level": "LOW",
  "risk_flags": [],
  "reasons": [
    "Profit target +10% reached",
    "RSI is overheated while position is profitable"
  ],
  "signal_hits": []
}
```

## Actions

| Action | Meaning |
|---|---|
| HOLD | Keep current position. |
| WATCH | No sell yet, but risk should be monitored. |
| SELL_25 | Sell 25% of current shares. |
| SELL_50 | Sell 50% of current shares. |
| SELL_ALL | Close the full position. |

## Rule Blocks

### 1. Profit Engine

- +10% profit: partial sell candidate.
- +20% profit: full sell candidate.

### 2. Stop Loss Engine

- -5% loss: hard stop.
- Configured stop-loss price: full sell.
- 2 ATR below entry: ATR stop.

### 3. Trailing Stop Engine

- Highest price - 2 ATR.
- If ATR is missing, uses 8% drawdown from highest price as a fallback.

### 4. Trend Engine

- Close below MA20.
- Close below MA60.
- Close below MA120.

### 5. Momentum Engine

- MACD dead cross.
- RSI >= 80 while profitable.
- RSI <= 30 while losing.

### 6. Time Exit

- Holding days >= 30 and profit < 3%.

### 7. Gap Risk

- Open price gap-down more than 5% versus previous close.

## Database

`exit_decisions` stores the final sell decision and can link to the related entry decision.

## Tests

```bash
pytest tests/test_exit_engine.py
```

Covered cases:

- +10% partial profit.
- +20% full profit taking.
- -5% hard stop.
- ATR stop.
- Trailing stop.
- MACD dead cross.
- RSI overheated.
- 30-day time exit.
- Gap-down risk.
- Candidate deterioration.
- Dict backward compatibility.
- Invalid inputs.

## v2.0 Expansion

Exit Decision Engine v2.0 should add:

- Multi-timeframe exit confirmation.
- Position scaling schedules.
- Volatility regime-aware trailing stop.
- Portfolio-level forced deleveraging.
- Slippage-aware sell order type selection.
