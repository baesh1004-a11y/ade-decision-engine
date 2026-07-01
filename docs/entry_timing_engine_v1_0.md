# ADE Engine #3: Entry Timing Engine v1.0

## Purpose

The Entry Timing Engine answers the third ADE question:

> When and at what price should the system enter?

Candidate Decision Engine selects candidates. Position Sizing Engine decides how much to buy. Entry Timing Engine decides whether the current daily setup is actionable.

## Scope of v1.0

v1.0 uses daily OHLCV and daily indicators only. It intentionally does not require intraday bars, orderbook data, or execution data so the repository remains executable with the current collectors.

## Inputs

```python
EntryTimingEngine().evaluate(
    df=enriched_daily_dataframe,
    candidate={
        "score": 90,
        "grade": "A",
        "action": "BUY_CANDIDATE",
        "confidence": 0.90,
        "risk_level": "LOW",
    },
    position={
        "recommended_weight": 0.10,
        "shares": 100,
    },
    market_regime="BULL",
)
```

## Output

```json
{
  "engine_version": "entry-timing-v1.0.0",
  "entry_score": 85,
  "action": "BUY_NOW",
  "order_type": "LIMIT",
  "entry_price": 113.0,
  "limit_price": 113.0,
  "risk_level": "LOW",
  "risk_flags": [],
  "reasons": [
    "Price is aligned with short/mid trend",
    "Price is breaking the 20-day high with volume expansion"
  ],
  "signal_hits": []
}
```

## Actions

| Action | Meaning |
|---|---|
| BUY_NOW | Current daily setup is actionable. |
| WAIT | Candidate is valid, but price should be improved. |
| WATCH | Setup is forming but not ready. |
| CANCEL | Entry is blocked by risk, weak candidate state, or no executable size. |

## Rule Blocks

### 1. Trend Engine

- Price aligned with MA20 / MA60.
- Price above MA120.
- Bullish close above MA20 support.

### 2. Breakout Engine

- 20-day high breakout.
- Volume expansion confirmation.

### 3. Pullback Engine

- Recent strength followed by pullback near MA20.
- Bullish support reaction.

### 4. Momentum Engine

- STO 5-3-3 upward turn before overheating.
- MACD cross above signal.
- RSI constructive zone, default 30 to 65.

### 5. Risk Gate

Entry is blocked or penalized when:

- Candidate risk is high.
- Position sizing returned zero executable shares.
- Strong bearish candle appears.
- Price is below MA120.
- Volume is weak.
- Bear market entry discount is required.

## Database

`entry_decisions` stores the final timing decision and links to candidate and position decisions when available.

## Tests

```bash
pytest tests/test_entry_engine.py
```

Covered cases:

- Breakout with volume.
- Pullback support.
- Bear market penalty.
- High candidate risk.
- No executable position.
- Bearish candle risk gate.
- Dict backward compatibility.
- Empty dataframe.
- Short dataframe.

## v2.0 Expansion

Entry Timing Engine v2.0 should add:

- 60-minute and 15-minute multi-timeframe confirmation.
- Orderbook imbalance.
- Trade intensity / execution strength.
- Gap handling.
- Slippage-aware order type selection.
