import pandas as pd

from backtest.execution import ExecutionCostModel
from backtest.metrics import MetricsEngine
from backtest.replay import ReplayEngine
from backtest.simulator import BacktestConfig, BacktestSimulator


def _market_data(rows: int = 180) -> pd.DataFrame:
    data = []
    for i in range(rows):
        close = 100 + i * 0.4
        data.append(
            {
                "Date": f"2024-01-{(i % 28) + 1:02d}",
                "Open": close - 0.2,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000 + i * 1000,
            }
        )
    return pd.DataFrame(data)


def test_replay_engine_yields_history_without_future_leakage():
    df = _market_data(120)
    frames = list(ReplayEngine(min_history=80).replay(df))

    assert len(frames) == 41
    assert len(frames[0].history) == 80
    assert len(frames[-1].history) == 120
    assert frames[0].history.iloc[-1]["Close"] == df.iloc[79]["Close"]


def test_backtest_simulator_returns_result_shape():
    result = BacktestSimulator(
        BacktestConfig(
            market="us",
            ticker="NVDA",
            initial_cash=100_000_000,
            min_history=100,
            max_holding_days=20,
            buy_score_threshold=40,
            buy_weight=0.10,
        )
    ).run(_market_data())

    assert result.ticker == "NVDA"
    assert result.initial_cash == 100_000_000
    assert result.final_equity > 0
    assert len(result.daily_equity) > 0
    assert isinstance(result.trades, list)


def test_execution_cost_model_applies_buy_and_sell_costs():
    model = ExecutionCostModel(commission_rate=0.001, slippage_rate=0.001, tax_rate=0.002)

    buy = model.apply_buy(price=100.0, shares=10)
    sell = model.apply_sell(price=100.0, shares=10)

    assert buy.gross_value == 1000.0
    assert buy.total_cost > buy.gross_value
    assert sell.net_value < sell.gross_value


def test_metrics_engine_summarizes_backtest_result():
    summary = MetricsEngine().summarize(
        {
            "total_return": 0.12,
            "max_drawdown": -0.05,
            "trades": [
                {"gross_return": 0.10},
                {"gross_return": -0.04},
                {"gross_return": 0.06},
            ],
        }
    )

    assert summary.trade_count == 3
    assert summary.win_rate == 0.6667
    assert summary.profit_factor > 1
    assert summary.expectancy > 0


def test_invalid_replay_rows_raise_value_error():
    try:
        list(ReplayEngine(min_history=80).replay(_market_data(rows=20)))
    except ValueError as exc:
        assert "at least" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
