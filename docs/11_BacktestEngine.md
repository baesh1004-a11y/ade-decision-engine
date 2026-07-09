# 11. Backtest Engine

## Purpose

Backtest Engine은 과거 시장 데이터를 사용해 ADE의 Signal, Risk, Decision, Order 로직을 검증한다. 이 엔진은 실계좌 주문을 절대 실행하지 않으며, 전략의 수익성, 손실 위험, 거래 빈도, 포트폴리오 변동성을 사전에 평가하는 검증 계층이다.

## Scope

Backtest Engine v1은 다음을 담당한다.

- 과거 OHLCV 데이터 로딩
- 지표 및 패턴 재계산
- 날짜별 신호 생성
- 리스크 한도 적용
- 의사결정 결과 시뮬레이션
- 가상 주문 및 체결 처리
- 포트폴리오 가치 변화 계산
- 성과 및 리스크 지표 산출
- 리포트 엔진으로 전달할 결과 저장

Backtest Engine은 다음을 담당하지 않는다.

- 실시간 주문 전송
- 실계좌 잔고 조회
- 실계좌 체결 추적
- KIS 실주문 API 호출
- 전략 자동 최적화 실행

## Position in ADE Architecture

```text
Historical Market Data
        ↓
DataHub Engine
        ↓
Data Quality Engine
        ↓
Signal Engine
        ↓
Risk Engine
        ↓
Decision Engine
        ↓
Simulated Order Engine
        ↓
Simulated Execution
        ↓
Simulated Portfolio State
        ↓
Backtest Metrics
        ↓
Report Engine
```

## Core Principles

1. Backtest uses the same decision path as live/paper execution whenever possible.
2. No live broker API call is allowed.
3. All simulated orders must be explicitly marked as `SIMULATED`.
4. Slippage, fees, taxes, and failed fills must be configurable.
5. Look-ahead bias must be prevented.
6. Results must be reproducible from the same config and data snapshot.
7. Backtest results are evidence, not proof of future performance.

## Inputs

| Input | Description |
|---|---|
| symbols | list of symbols to test |
| start_date | backtest start date |
| end_date | backtest end date |
| initial_cash | starting virtual cash |
| strategy_config | signal/risk/decision parameters |
| fee_config | commission, tax, market impact assumptions |
| execution_config | fill rule, slippage model, partial fill rule |
| benchmark | optional benchmark index or ETF |

## Output

```python
BacktestResult(
    run_id="bt_20260709_001",
    start_date="2023-01-01",
    end_date="2025-12-31",
    initial_cash=100000000,
    final_equity=128500000,
    total_return=0.285,
    cagr=0.087,
    max_drawdown=-0.142,
    sharpe_ratio=1.18,
    win_rate=0.54,
    total_trades=126,
    status="COMPLETED"
)
```

## Main Components

| Component | Responsibility |
|---|---|
| BacktestRunner | 전체 백테스트 실행 제어 |
| HistoricalDataLoader | 과거 데이터 로딩 및 정렬 |
| SimulationClock | 날짜/시간 단위 진행 제어 |
| StrategyReplay | Signal/Risk/Decision 로직 재사용 |
| SimulatedOrderBook | 가상 주문 생성 및 상태 관리 |
| FillSimulator | 체결가, 슬리피지, 부분체결 계산 |
| PortfolioSimulator | 현금, 포지션, 평가금액 계산 |
| MetricsCalculator | 수익률, MDD, 변동성, 승률 계산 |
| BacktestRepository | 실행 결과와 거래 내역 저장 |

## Database Design

### backtest_runs

| Column | Type | Description |
|---|---|---|
| run_id | TEXT PK | backtest run id |
| created_at | TIMESTAMP | creation time |
| start_date | DATE | test start |
| end_date | DATE | test end |
| initial_cash | NUMERIC | starting cash |
| final_equity | NUMERIC | ending equity |
| total_return | NUMERIC | total return |
| cagr | NUMERIC | compound annual growth rate |
| max_drawdown | NUMERIC | maximum drawdown |
| sharpe_ratio | NUMERIC | risk-adjusted return |
| win_rate | NUMERIC | profitable trade ratio |
| total_trades | INTEGER | number of closed trades |
| status | TEXT | PENDING/RUNNING/COMPLETED/FAILED |
| config_hash | TEXT | reproducibility hash |
| notes | TEXT | run notes |

### backtest_daily_equity

| Column | Type | Description |
|---|---|---|
| run_id | TEXT FK | backtest run id |
| trade_date | DATE | date |
| cash | NUMERIC | virtual cash |
| market_value | NUMERIC | position value |
| total_equity | NUMERIC | cash + market value |
| daily_return | NUMERIC | daily return |
| drawdown | NUMERIC | drawdown from peak |

### backtest_trades

| Column | Type | Description |
|---|---|---|
| trade_id | TEXT PK | trade id |
| run_id | TEXT FK | backtest run id |
| symbol | TEXT | traded symbol |
| side | TEXT | BUY/SELL |
| order_date | DATE | simulated order date |
| fill_date | DATE | simulated fill date |
| order_price | NUMERIC | intended price |
| fill_price | NUMERIC | simulated fill price |
| quantity | INTEGER | filled quantity |
| fee | NUMERIC | commission |
| tax | NUMERIC | tax |
| slippage | NUMERIC | slippage amount |
| reason | TEXT | decision reason |

### backtest_positions

| Column | Type | Description |
|---|---|---|
| run_id | TEXT FK | backtest run id |
| trade_date | DATE | date |
| symbol | TEXT | symbol |
| quantity | INTEGER | quantity |
| avg_price | NUMERIC | average price |
| close_price | NUMERIC | daily close |
| market_value | NUMERIC | valuation |
| unrealized_pnl | NUMERIC | unrealized profit/loss |

### backtest_signals

| Column | Type | Description |
|---|---|---|
| run_id | TEXT FK | backtest run id |
| trade_date | DATE | signal date |
| symbol | TEXT | symbol |
| signal_score | NUMERIC | signal score |
| risk_score | NUMERIC | risk score |
| decision | TEXT | BUY/HOLD/REDUCE/SELL/REJECT/NO_ACTION |
| reason | TEXT | explanation |

## Algorithm

### 1. Initialize

```python
run = create_backtest_run(config)
portfolio = PortfolioSimulator(initial_cash=config.initial_cash)
clock = SimulationClock(start_date, end_date)
```

### 2. Load and Validate Historical Data

```python
bars = datahub.load_history(symbols, start_date, end_date)
validated = quality_engine.validate(bars)
```

Validation must reject or flag:

- missing OHLCV rows
- duplicated dates
- non-positive prices
- abnormal volume gaps
- insufficient lookback window

### 3. Replay Strategy by Date

```python
for date in clock:
    market_slice = bars.up_to(date)
    indicators = indicator_engine.compute(market_slice)
    signals = signal_engine.score(indicators)
    risk = risk_engine.evaluate(signals, portfolio.snapshot(date))
    decisions = decision_engine.decide(signals, risk, portfolio.snapshot(date))
```

Rule: only data available up to the current simulated date may be used.

### 4. Generate Simulated Orders

```python
orders = simulated_order_engine.create(decisions, mode="SIMULATED")
```

The order engine must not call KIS or any live broker connector.

### 5. Simulate Fills

```python
fills = fill_simulator.apply(
    orders,
    next_bar=bars.next_bar(date),
    slippage=config.slippage,
    fee=config.fee,
    tax=config.tax,
)
```

Default fill policy:

| Order Type | v1 Fill Rule |
|---|---|
| MARKET | next open price + slippage |
| LIMIT BUY | fill if next low <= limit price |
| LIMIT SELL | fill if next high >= limit price |
| STOP | fill if stop trigger touched |

### 6. Update Portfolio

```python
portfolio.apply_fills(fills)
portfolio.mark_to_market(date, close_prices)
repository.save_daily_equity(portfolio.snapshot(date))
```

### 7. Calculate Metrics

```python
metrics = metrics_calculator.calculate(equity_curve, trades, benchmark)
repository.complete_run(run_id, metrics)
```

## Metrics

| Metric | Meaning |
|---|---|
| Total Return | total profit/loss percentage |
| CAGR | annualized return |
| Max Drawdown | largest peak-to-trough loss |
| Volatility | standard deviation of returns |
| Sharpe Ratio | return per unit risk |
| Sortino Ratio | downside-risk adjusted return |
| Win Rate | profitable closed trades ratio |
| Profit Factor | gross profit / gross loss |
| Average Holding Days | average trade duration |
| Turnover | trading intensity |
| Exposure Ratio | invested capital ratio |

## Bias and Safety Controls

| Risk | Control |
|---|---|
| Look-ahead bias | use only data available at simulated date |
| Survivorship bias | store tested universe snapshot |
| Overfitting | separate train/validation/test periods |
| Unrealistic fills | configurable slippage and partial fills |
| Fee omission | mandatory fee/tax config |
| Live order leakage | force `SIMULATED` mode and block broker calls |
| Non-reproducible result | persist config hash and data snapshot id |

## Code Structure

```text
backtest/
  __init__.py
  runner.py
  clock.py
  data_loader.py
  fill.py
  portfolio.py
  metrics.py
  repository.py
  models.py

tests/
  test_backtest_runner.py
  test_fill_simulator.py
  test_backtest_metrics.py
  test_no_lookahead.py
```

## Interface Draft

```python
@dataclass
class BacktestConfig:
    symbols: list[str]
    start_date: date
    end_date: date
    initial_cash: float
    benchmark: str | None = None
    fee_rate: float = 0.00015
    tax_rate: float = 0.0018
    slippage_bps: float = 5.0
    max_positions: int = 10


class BacktestRunner:
    def run(self, config: BacktestConfig) -> BacktestResult:
        """Run full ADE strategy replay using historical data."""
        raise NotImplementedError
```

## Test Plan

### Unit Tests

- creates backtest run with valid config
- rejects end_date earlier than start_date
- rejects missing historical data
- fill simulator handles market order at next open
- limit buy fills only when next low touches limit
- limit sell fills only when next high touches limit
- fee and tax reduce net proceeds
- portfolio cash decreases after buy fill
- portfolio cash increases after sell fill
- max drawdown calculation is correct
- CAGR calculation is correct
- no data after current simulation date is accessible

### Integration Tests

- run full backtest on small fixture dataset
- Signal/Risk/Decision path produces deterministic results
- simulated orders do not call live broker connector
- daily equity is saved for every trading day
- trades and positions are persisted correctly
- completed run contains final metrics

### Regression Tests

- same config and same data snapshot produce same result
- higher slippage lowers or preserves total return
- higher fee lowers or preserves total return
- insufficient lookback returns no trade or controlled failure

## Acceptance Criteria

Backtest Engine v1 is considered implemented when:

1. A full backtest can run from historical data to metrics.
2. Daily equity, trades, positions, and signals are persisted.
3. Live order APIs are unreachable from the backtest path.
4. Look-ahead bias prevention is covered by tests.
5. Result metrics are reproducible for the same config.
6. Report Engine can consume the saved backtest result.

## Next Step

After Backtest Engine v1 design, Report Engine v1 should be designed to consume:

- daily decisions
- orders
- executions
- portfolio state
- backtest results
- risk events
