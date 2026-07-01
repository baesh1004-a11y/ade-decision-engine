# ADE Engine #6: Risk Engine v1.0

## Purpose

The Risk Engine is the account survival layer of ADE.

It answers:

> Should the system allow new trades, reduce risk, pause trading, or force deleveraging?

## Scope of v1.0

v1.0 supports:

- Daily loss stop.
- Max drawdown warning and hard stop.
- Portfolio heat limit.
- VIX high/crisis regime.
- Bear-market defensive mode.
- Consecutive loss-streak reduction.
- New-position size cap.
- Target cash adjustment.

## Input

```python
RiskInput(
    account_balance=100_000_000,
    equity_peak=110_000_000,
    daily_pnl=-1_000_000,
    portfolio_heat=0.04,
    cash_weight=0.20,
    vix=25,
    market_regime="SIDEWAY",
    consecutive_losses=1,
)
```

## Output

```json
{
  "engine_version": "risk-engine-v1.0.0",
  "risk_score": 35,
  "risk_level": "MEDIUM",
  "action": "LIMIT_NEW_TRADES",
  "trade_allowed": true,
  "max_new_position_weight": 0.06,
  "target_cash_weight": 0.30,
  "daily_loss_pct": -0.01,
  "drawdown_pct": -0.09,
  "risk_flags": [],
  "reasons": []
}
```

## Actions

| Action | Meaning |
|---|---|
| ALLOW_TRADING | Normal trading allowed. |
| LIMIT_NEW_TRADES | Allow only reduced-size new trades. |
| REDUCE_RISK | Reduce position size and risk exposure. |
| PAUSE_TRADING | Stop new trading for the day. |
| FORCE_DELEVERAGE | Raise cash aggressively and reduce exposure. |

## Core Rules

### Daily Loss Stop

Default:

```text
-3% daily loss → PAUSE_TRADING
```

### Max Drawdown

Default:

```text
-10% MDD → warning / reduce risk
-15% MDD → FORCE_DELEVERAGE
```

### Portfolio Heat

Default:

```text
portfolio_heat >= 6% → risk limit breached
```

### VIX Regime

```text
VIX >= 30 → high regime
VIX >= 40 → crisis regime / FORCE_DELEVERAGE
```

### Market Regime

```text
BULL    target cash 10%
SIDEWAY target cash 20%
BEAR    target cash 50%
```

### New Position Cap

| Risk Level | Max New Position Weight |
|---|---:|
| LOW | 10% |
| MEDIUM | 6% |
| HIGH | 3% |
| CRITICAL | 0% |

## Database

`risk_decisions` stores daily account-level risk decisions.

## Tests

```bash
pytest tests/test_risk_engine.py
```

Covered cases:

- Low risk allows trading.
- Daily stop loss pauses trading.
- Max drawdown hard stop forces deleveraging.
- Drawdown warning reduces risk.
- VIX crisis forces deleveraging.
- Portfolio heat limits new trades.
- Bear market raises target cash.
- Consecutive loss streak.
- Dict payload compatibility.
- Invalid inputs.

## v2.0 Expansion

Risk Engine v2.0 should add:

- Portfolio correlation shock.
- Sector crash detection.
- Intraday loss monitoring.
- Forced liquidation priority.
- Broker/order execution integration.
- Automatic risk budget feedback to Position Sizing Engine.
