from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PerformanceSummary:
    trade_count: int
    win_rate: float
    avg_return: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    expectancy: float
    total_return: float
    max_drawdown: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MetricsEngine:
    """Compute core performance metrics from backtest result dictionaries."""

    def summarize(self, result: dict[str, Any]) -> PerformanceSummary:
        trades = result.get("trades", [])
        returns = [float(trade.get("gross_return", 0.0)) for trade in trades]
        wins = [ret for ret in returns if ret > 0]
        losses = [ret for ret in returns if ret < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
        trade_count = len(returns)
        win_rate = len(wins) / trade_count if trade_count else 0.0
        avg_return = sum(returns) / trade_count if trade_count else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss if trade_count else 0.0

        return PerformanceSummary(
            trade_count=trade_count,
            win_rate=round(win_rate, 4),
            avg_return=round(avg_return, 4),
            avg_win=round(avg_win, 4),
            avg_loss=round(avg_loss, 4),
            profit_factor=round(profit_factor, 4),
            expectancy=round(expectancy, 4),
            total_return=round(float(result.get("total_return", 0.0)), 4),
            max_drawdown=round(float(result.get("max_drawdown", 0.0)), 4),
        )
