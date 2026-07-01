# ADE v1.0 Integrated Pipeline

## Purpose

ADE v1.0 is now organized as a full decision pipeline instead of separate standalone engines.

The key change is the introduction of `DecisionContext`.

`DecisionContext` carries market data, account state, risk state, position state, holdings, learning samples, and each engine's output through the full pipeline.

## Execution Order

```text
Market Data
    ↓
Indicator Pipeline
    ↓
Candidate Decision Engine
    ↓
Risk Engine
    ↓
Position Sizing Engine
    ↓
Entry Timing Engine
    ↓
Exit Decision Engine        optional, when current_position exists
    ↓
Portfolio Manager Engine    optional, when holdings exist
    ↓
Learning Engine             optional, when learning_samples exist
```

## Why Risk Runs Before Position

The Risk Engine must run before Position Sizing because account-level risk can override single-symbol sizing.

Example:

```text
Position Sizing says: 10%
Risk Engine says: max new position 3%
Final position: 3%
```

This prevents the system from taking oversized trades during drawdown, high VIX, high portfolio heat, or bear-market conditions.

## Core Files

```text
core/context.py
core/pipeline.py
core/__init__.py
```

## Example

```python
import pandas as pd

from core.context import DecisionContext
from core.pipeline import ADEPipeline

context = DecisionContext(
    market="us",
    ticker="NVDA",
    market_data=df,
    account_balance=100_000_000,
    cash=50_000_000,
    equity_peak=105_000_000,
    daily_pnl=-500_000,
    portfolio_heat=0.03,
    market_regime="SIDEWAY",
    vix=22,
)

result = ADEPipeline().run(context)
print(result.to_dict())
```

## Output Shape

```json
{
  "market": "us",
  "ticker": "NVDA",
  "decisions": {
    "candidate": {},
    "risk": {},
    "position": {},
    "entry": {},
    "exit": {},
    "portfolio": {},
    "learning": {}
  },
  "errors": []
}
```

## Error Boundary

The core chain always runs:

```text
Candidate → Risk → Position → Entry
```

Optional engines are isolated:

```text
Exit
Portfolio
Learning
```

If an optional engine fails, the error is added to `context.errors` without stopping the core decision chain.

## Tests

```bash
pytest tests/test_ade_pipeline.py
pytest
```

Covered cases:

- Core pipeline runs Candidate, Risk, Position, Entry.
- Risk Engine caps new position size.
- Optional Exit, Portfolio, Learning engines run when inputs exist.
- DecisionContext serializes final output.

## Current Limitation

`main.py` still exposes the legacy CLI flow. The new `ADEPipeline` is ready for API/service integration and should become the preferred runtime entry point in the next refactor.

## Next Refactor

Recommended next steps:

1. Move `main.py` to use `ADEPipeline` directly.
2. Add `engine_parameters` table.
3. Add `engine_metrics` table.
4. Add JSON report writer.
5. Add dashboard/API boundary.
