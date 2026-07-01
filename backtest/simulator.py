from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtest.execution import ExecutionCostModel
from backtest.models import BacktestPosition, BacktestResult, DailyEquity, TradeRecord
from backtest.replay import ReplayEngine
from core.context import DecisionContext
from core.pipeline import ADEPipeline
from pattern.memory import PatternMemoryRepository


@dataclass(frozen=True)
class BacktestConfig:
    market: str
    ticker: str
    initial_cash: float = 100_000_000
    min_history: int = 100
    max_holding_days: int = 20
    buy_score_threshold: int = 70
    buy_weight: float = 0.10
    commission_rate: float = 0.00015
    slippage_rate: float = 0.0005
    tax_rate: float = 0.0


class BacktestSimulator:
    """ADE Backtesting Engine v1.1: replay + cost-aware long-only simulation."""

    def __init__(self, config: BacktestConfig) -> None:
        if config.initial_cash <= 0:
            raise ValueError("initial_cash must be greater than zero")
        if config.buy_weight <= 0 or config.buy_weight > 1:
            raise ValueError("buy_weight must be between 0 and 1")
        self.config = config
        self.replay = ReplayEngine(min_history=config.min_history)
        self.execution = ExecutionCostModel(
            commission_rate=config.commission_rate,
            slippage_rate=config.slippage_rate,
            tax_rate=config.tax_rate,
        )
        self.memory_repository = PatternMemoryRepository()
        self.pipeline = ADEPipeline(memory_repository=self.memory_repository, auto_build_memory=True)

    def run(self, df: pd.DataFrame) -> BacktestResult:
        frames = list(self.replay.replay(df))
        cash = self.config.initial_cash
        position: BacktestPosition | None = None
        trades: list[TradeRecord] = []
        daily: list[DailyEquity] = []
        equity_peak = self.config.initial_cash

        for frame in frames:
            close = float(frame.history.iloc[-1]["Close"])
            context = DecisionContext(
                market=self.config.market,
                ticker=self.config.ticker,
                market_data=frame.history,
                account_balance=max(cash + self._position_value(position, close), 1.0),
                cash=cash,
                equity_peak=equity_peak,
                market_regime="SIDEWAY",
                current_position=self._position_context(position, close),
            )
            result = self.pipeline.run(context)
            candidate = result.decisions.get("candidate", {})
            entry = result.decisions.get("entry", {})
            exit_decision = result.decisions.get("exit", {})

            if position is None and self._should_buy(candidate, entry):
                buy_budget = min(cash, self.config.initial_cash * self.config.buy_weight)
                shares = int(buy_budget // close)
                if shares > 0:
                    buy_exec = self.execution.apply_buy(close, shares)
                    if buy_exec.total_cost <= cash:
                        cash -= buy_exec.total_cost
                        position = BacktestPosition(
                            ticker=self.config.ticker,
                            entry_date=frame.trade_date,
                            entry_price=close,
                            shares=shares,
                            entry_value=buy_exec.total_cost,
                            highest_price=close,
                        )
            elif position is not None:
                position.holding_days += 1
                position.highest_price = max(position.highest_price, close)
                if self._should_exit(position, exit_decision):
                    sell_exec = self.execution.apply_sell(close, position.shares)
                    cash += sell_exec.net_value
                    trades.append(
                        TradeRecord(
                            ticker=self.config.ticker,
                            entry_date=position.entry_date,
                            exit_date=frame.trade_date,
                            entry_price=position.entry_price,
                            exit_price=close,
                            shares=position.shares,
                            gross_return=(close - position.entry_price) / position.entry_price,
                            holding_days=position.holding_days,
                            reason=str(exit_decision.get("action", "TIME_EXIT")),
                            metadata={
                                "candidate": candidate,
                                "exit": exit_decision,
                                "sell_execution": sell_exec.to_dict(),
                            },
                        )
                    )
                    position = None

            equity = cash + self._position_value(position, close)
            equity_peak = max(equity_peak, equity)
            drawdown = (equity - equity_peak) / equity_peak if equity_peak > 0 else 0.0
            daily.append(
                DailyEquity(
                    trade_date=frame.trade_date,
                    cash=round(cash, 2),
                    position_value=round(self._position_value(position, close), 2),
                    equity=round(equity, 2),
                    drawdown=round(drawdown, 4),
                )
            )

        final_equity = daily[-1].equity if daily else self.config.initial_cash
        wins = [trade for trade in trades if trade.gross_return > 0]
        return BacktestResult(
            ticker=self.config.ticker,
            start_date=frames[0].trade_date if frames else "",
            end_date=frames[-1].trade_date if frames else "",
            initial_cash=self.config.initial_cash,
            final_equity=round(final_equity, 2),
            total_return=round((final_equity - self.config.initial_cash) / self.config.initial_cash, 4),
            max_drawdown=round(min((d.drawdown for d in daily), default=0.0), 4),
            trade_count=len(trades),
            win_rate=round(len(wins) / len(trades), 4) if trades else 0.0,
            trades=[trade.to_dict() for trade in trades],
            daily_equity=[item.to_dict() for item in daily],
            reasons=["Backtest v1.1 uses long-only fixed-weight simulation with execution costs"],
        )

    def _position_value(self, position: BacktestPosition | None, close: float) -> float:
        return position.shares * close if position else 0.0

    def _position_context(self, position: BacktestPosition | None, close: float) -> dict[str, Any] | None:
        if position is None:
            return None
        return {
            "entry_price": position.entry_price,
            "shares": position.shares,
            "highest_price": position.highest_price,
            "holding_days": position.holding_days,
            "stop_loss_price": position.entry_price * 0.92,
        }

    def _should_buy(self, candidate: dict[str, Any], entry: dict[str, Any]) -> bool:
        score = int(candidate.get("score", 0))
        entry_action = str(entry.get("action", ""))
        return score >= self.config.buy_score_threshold and entry_action not in {"WAIT", "AVOID"}

    def _should_exit(self, position: BacktestPosition, exit_decision: dict[str, Any]) -> bool:
        action = str(exit_decision.get("action", "HOLD"))
        if action in {"SELL_ALL", "EXIT", "STOP_LOSS", "TAKE_PROFIT"}:
            return True
        return position.holding_days >= self.config.max_holding_days
