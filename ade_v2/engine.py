"""Deterministic, broker-independent ADE v2 planning and fill accounting.

No order is considered filled until a confirmed fill is explicitly applied.
All amounts are KRW; cash must be settled/available before reuse.
"""
from dataclasses import dataclass, field
from math import floor, isfinite


@dataclass(frozen=True)
class Policy:
    initial_capital: int = 10_000_000
    target_turnover: int = 15_000_000
    min_cash_ratio: float = 0.10
    max_weight: float = 0.10
    fee_rate: float = 0.00015
    sell_tax_rate: float = 0.0018


@dataclass(frozen=True)
class Signal:
    ticker: str
    price: float
    predicted_return: float
    downside_risk: float
    confidence: float = 1.0
    exit_signal: bool = False


@dataclass(frozen=True)
class Order:
    ticker: str
    side: str
    quantity: int
    reference_price: float
    reason: str


@dataclass
class Ledger:
    settled_cash: float
    positions: dict[str, int] = field(default_factory=dict)
    cost_basis: dict[str, float] = field(default_factory=dict)
    realized_pnl: float = 0.0
    turnover: float = 0.0
    pending_settlement: float = 0.0

    def nav(self, prices: dict[str, float]) -> float:
        return self.settled_cash + self.pending_settlement + sum(
            qty * prices[ticker] for ticker, qty in self.positions.items()
        )

    def apply_confirmed_fill(self, order: Order, fill_price: float, policy: Policy,
                             *, mark_prices: dict[str, float] | None = None) -> None:
        """Apply a verified fill only. Sells remain unsettled until settle() is called.

        BUY fills require contemporaneous prices for *all* existing positions.
        This fails closed when a fill price would breach cash/position limits
        after transaction fees. The fill price is authoritative for accounting.
        """
        if not isfinite(fill_price) or fill_price <= 0 or order.quantity <= 0:
            raise ValueError("Invalid confirmed fill")
        gross = fill_price * order.quantity
        fee = gross * policy.fee_rate
        if order.side == "BUY":
            debit = gross + fee
            if debit > self.settled_cash + 1e-8:
                raise ValueError("Insufficient settled cash")
            if mark_prices is None:
                raise ValueError("Mark prices required for post-fill risk checks")
            prices = dict(mark_prices)
            prices[order.ticker] = fill_price
            if any(not isfinite(p) or p <= 0 for p in prices.values()):
                raise ValueError("Invalid mark price")
            try:
                nav_after_fees = self.nav(prices) - fee
            except KeyError as exc:
                raise ValueError("Missing mark price for held position") from exc
            if nav_after_fees <= 0:
                raise ValueError("Nonpositive NAV")
            if self.settled_cash - debit < policy.min_cash_ratio * nav_after_fees - 1e-8:
                raise ValueError("Minimum settled cash reserve breached")
            position_after = (self.positions.get(order.ticker, 0) + order.quantity) * fill_price
            if position_after > policy.max_weight * nav_after_fees + 1e-8:
                raise ValueError("Maximum position weight breached")
            self.settled_cash -= debit
            old_qty = self.positions.get(order.ticker, 0)
            old_cost = self.cost_basis.get(order.ticker, 0.0)
            self.positions[order.ticker] = old_qty + order.quantity
            self.cost_basis[order.ticker] = old_cost + debit
        elif order.side == "SELL":
            old_qty = self.positions.get(order.ticker, 0)
            if order.quantity > old_qty:
                raise ValueError("Cannot sell more than held")
            old_cost = self.cost_basis.get(order.ticker, 0.0)
            allocated_cost = old_cost * order.quantity / old_qty
            proceeds = gross - fee - gross * policy.sell_tax_rate
            self.realized_pnl += proceeds - allocated_cost
            self.positions[order.ticker] = old_qty - order.quantity
            self.cost_basis[order.ticker] = old_cost - allocated_cost
            self.pending_settlement += proceeds
        else:
            raise ValueError("Unknown side")
        self.turnover += gross

    def settle(self, amount: float) -> None:
        if amount < 0 or amount > self.pending_settlement + 1e-8:
            raise ValueError("Invalid settlement")
        self.pending_settlement -= amount
        self.settled_cash += amount


def rank_signals(signals: list[Signal], policy: Policy) -> list[Signal]:
    """Risk-adjusted, after-cost score; never claims to predict true returns."""
    for s in signals:
        if not all(isfinite(x) for x in (s.price, s.predicted_return, s.downside_risk, s.confidence)):
            raise ValueError("Nonfinite signal")
        if s.price <= 0 or s.downside_risk < 0 or not 0 <= s.confidence <= 1:
            raise ValueError("Invalid signal")
    friction = 2 * policy.fee_rate + policy.sell_tax_rate
    return sorted(signals, key=lambda s: (
        s.confidence * s.predicted_return - s.downside_risk - friction
    ), reverse=True)


def plan_orders(ledger: Ledger, prices: dict[str, float],
                signals: list[Signal], policy: Policy = Policy()) -> tuple[list[Order], dict[str, str]]:
    """Risk-first plan; sells precede buys, but unsettled proceeds cannot fund buys."""
    nav = ledger.nav(prices)
    if nav <= 0:
        return [], {"portfolio": "NONPOSITIVE_NAV"}
    reserve = nav * policy.min_cash_ratio
    orders: list[Order] = []
    reasons: dict[str, str] = {}
    held = dict(ledger.positions)
    available = ledger.settled_cash
    for s in signals:
        if s.exit_signal and held.get(s.ticker, 0):
            orders.append(Order(s.ticker, "SELL", held[s.ticker], s.price, "EXIT_SIGNAL"))
            reasons[s.ticker] = "SELL_SIGNAL"
    friction = 2 * policy.fee_rate + policy.sell_tax_rate
    for s in rank_signals([x for x in signals if not x.exit_signal], policy):
        if s.confidence * s.predicted_return - s.downside_risk <= friction:
            reasons[s.ticker] = "NONPOSITIVE_NET_EDGE"
            continue
        existing_value = held.get(s.ticker, 0) * s.price
        capacity = max(0.0, policy.max_weight * nav - existing_value)
        cash_capacity = max(0.0, available - reserve)
        quantity = max(0, floor(min(capacity, cash_capacity) / (s.price * (1 + policy.fee_rate))))
        if quantity == 0:
            reasons[s.ticker] = "CASH_OR_WEIGHT_LIMIT"
            continue
        orders.append(Order(s.ticker, "BUY", quantity, s.price, "POSITIVE_RISK_ADJUSTED_EDGE"))
        available -= quantity * s.price * (1 + policy.fee_rate)
        held[s.ticker] = held.get(s.ticker, 0) + quantity
        reasons[s.ticker] = "BUY_CANDIDATE"
    return orders, reasons
