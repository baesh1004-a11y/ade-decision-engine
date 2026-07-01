# ADE Backtesting Engine v1

## Purpose

Backtesting Engine turns ADE from a decision system into a verification system.

It answers:

```text
If ADE had made decisions in the past, what would have happened?
```

## Implemented Stages

### v1.0 Replay + Basic Simulation

```text
Historical OHLCV
  ↓
ReplayEngine
  ↓
ADEPipeline per date
  ↓
Candidate / Entry / Exit decision
  ↓
Basic long-only simulation
```

### v1.1 Execution Cost Engine

Adds:

```text
Commission
Slippage
Sell-side tax
```

### v1.2 Metrics Engine

Adds:

```text
Trade count
Win rate
Average return
Average win/loss
Profit factor
Expectancy
Total return
Max drawdown
```

### v1.3 Persistence Engine

Adds SQLite persistence for:

```text
backtest_runs_v2
backtest_trades
backtest_daily_equity
backtest_performance_summary
```

## Core Files

```text
backtest/replay.py
backtest/models.py
backtest/execution.py
backtest/simulator.py
backtest/metrics.py
backtest/persistence.py
database/migrations/002_add_backtest_persistence.sql
tests/test_backtest_engine.py
```

## Example

```python
from backtest.simulator import BacktestConfig, BacktestSimulator
from backtest.metrics import MetricsEngine
from backtest.persistence import BacktestRepository

config = BacktestConfig(
    market="us",
    ticker="NVDA",
    initial_cash=100_000_000,
    min_history=100,
    max_holding_days=20,
    buy_score_threshold=70,
    buy_weight=0.10,
    commission_rate=0.00015,
    slippage_rate=0.0005,
    tax_rate=0.0,
)

result = BacktestSimulator(config).run(df)
summary = MetricsEngine().summarize(result.to_dict())
run_id = BacktestRepository("ade.db").save_result(result)
```

## Output

`BacktestResult` includes:

```text
ticker
start_date
end_date
initial_cash
final_equity
total_return
max_drawdown
trade_count
win_rate
trades
daily_equity
```

## Persistence Output

`BacktestRepository.fetch_run(run_id)` returns:

```text
run
trades
daily_equity
summary
```

## Current Limitations

v1 is intentionally simple:

```text
Single ticker
Long-only
Fixed buy weight
Time-based max holding exit
No portfolio-level multi-position simulation yet
No broker order book model
```

## Next Stages

### v1.4 Report Engine

Generate human-readable backtest reports.

### v2.0 Calibration

Use backtest results to calibrate Probability Engine and Adaptive Learning.
