"""Fail-closed settlement tracking. No brokerage orders or automatic cash release."""
from dataclasses import dataclass, field
from datetime import date
from math import isfinite


@dataclass(frozen=True)
class PendingCredit:
    fill_id: str
    amount: float
    due_date: date


@dataclass
class SettlementBook:
    pending: dict[str, PendingCredit] = field(default_factory=dict)
    settled_ids: set[str] = field(default_factory=set)

    def register(self, credit: PendingCredit) -> None:
        if not credit.fill_id or not isfinite(credit.amount) or credit.amount <= 0:
            raise ValueError("Invalid settlement credit")
        if credit.fill_id in self.pending or credit.fill_id in self.settled_ids:
            raise ValueError("Duplicate settlement credit")
        self.pending[credit.fill_id] = credit

    def confirm(self, fill_id: str, *, as_of: date, broker_confirmed: bool) -> float:
        if fill_id in self.settled_ids:
            raise ValueError("Already settled")
        if fill_id not in self.pending:
            raise ValueError("Unknown settlement credit")
        credit = self.pending[fill_id]
        if as_of < credit.due_date or not broker_confirmed:
            raise ValueError("Settlement not verified or not due")
        del self.pending[fill_id]
        self.settled_ids.add(fill_id)
        return credit.amount


def due_date(trade_date: date, exchange_sessions: list[date], lag: int = 2) -> date:
    """Caller must supply a complete, verified exchange-session calendar."""
    if lag < 1 or exchange_sessions != sorted(set(exchange_sessions)):
        raise ValueError("Invalid session calendar")
    if trade_date not in exchange_sessions:
        raise ValueError("Trade date not in verified exchange calendar")
    idx = exchange_sessions.index(trade_date) + lag
    if idx >= len(exchange_sessions):
        raise ValueError("Insufficient future exchange sessions")
    return exchange_sessions[idx]
