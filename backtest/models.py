from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BacktestPosition:
    ticker: str
    entry_date: str
    entry_price: float
    shares: int
    entry_value: float
    highest_price: float
    holding_days: int = 0


@dataclass(frozen=True)
class TradeRecord:
    ticker: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: int
    gross_return: float
    holding_days: int
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DailyEquity:
    trade_date: str
    cash: float
    position_value: float
    equity: float
    drawdown: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestResult:
    ticker: str
    start_date: str
    end_date: str
    initial_cash: float
    final_equity: float
    total_return: float
    max_drawdown: float
    trade_count: int
    win_rate: float
    trades: list[dict[str, Any]]
    daily_equity: list[dict[str, Any]]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
