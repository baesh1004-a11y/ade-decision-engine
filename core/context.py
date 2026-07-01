from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


@dataclass
class DecisionContext:
    """Shared state passed across ADE engines.

    Engines can read the same market/account context and attach their decisions
    without mutating each other's payload shapes. This keeps the full decision
    chain auditable.
    """

    market: str
    ticker: str
    market_data: pd.DataFrame
    account_balance: float
    cash: float
    market_regime: str = "SIDEWAY"
    vix: float | None = None
    equity_peak: float | None = None
    daily_pnl: float = 0.0
    portfolio_heat: float = 0.0
    holdings: list[dict[str, Any]] = field(default_factory=list)
    current_position: dict[str, Any] | None = None
    learning_samples: list[dict[str, Any]] = field(default_factory=list)
    decisions: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def add_decision(self, name: str, decision: Any) -> None:
        if hasattr(decision, "to_dict"):
            self.decisions[name] = decision.to_dict()
        elif hasattr(decision, "__dict__"):
            self.decisions[name] = asdict(decision)
        else:
            self.decisions[name] = decision

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def get_decision(self, name: str) -> dict[str, Any] | None:
        decision = self.decisions.get(name)
        return decision if isinstance(decision, dict) else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "ticker": self.ticker,
            "account_balance": self.account_balance,
            "cash": self.cash,
            "market_regime": self.market_regime,
            "vix": self.vix,
            "equity_peak": self.equity_peak,
            "daily_pnl": self.daily_pnl,
            "portfolio_heat": self.portfolio_heat,
            "holdings": self.holdings,
            "current_position": self.current_position,
            "decisions": self.decisions,
            "errors": self.errors,
        }
