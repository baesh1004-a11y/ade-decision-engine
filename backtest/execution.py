from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ExecutionResult:
    side: str
    price: float
    shares: int
    gross_value: float
    commission: float
    slippage: float
    tax: float
    total_cost: float
    net_value: float

    def to_dict(self) -> dict:
        return asdict(self)


class ExecutionCostModel:
    """Simple execution cost model for backtests.

    v1.1 supports commission, slippage, and sell-side tax.
    """

    def __init__(
        self,
        commission_rate: float = 0.00015,
        slippage_rate: float = 0.0005,
        tax_rate: float = 0.0,
    ) -> None:
        if commission_rate < 0 or slippage_rate < 0 or tax_rate < 0:
            raise ValueError("cost rates cannot be negative")
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.tax_rate = tax_rate

    def apply_buy(self, price: float, shares: int) -> ExecutionResult:
        self._validate(price, shares)
        gross = price * shares
        commission = gross * self.commission_rate
        slippage = gross * self.slippage_rate
        tax = 0.0
        total_cost = gross + commission + slippage + tax
        return ExecutionResult(
            side="BUY",
            price=price,
            shares=shares,
            gross_value=round(gross, 2),
            commission=round(commission, 2),
            slippage=round(slippage, 2),
            tax=round(tax, 2),
            total_cost=round(total_cost, 2),
            net_value=round(gross, 2),
        )

    def apply_sell(self, price: float, shares: int) -> ExecutionResult:
        self._validate(price, shares)
        gross = price * shares
        commission = gross * self.commission_rate
        slippage = gross * self.slippage_rate
        tax = gross * self.tax_rate
        total_cost = commission + slippage + tax
        net_value = gross - total_cost
        return ExecutionResult(
            side="SELL",
            price=price,
            shares=shares,
            gross_value=round(gross, 2),
            commission=round(commission, 2),
            slippage=round(slippage, 2),
            tax=round(tax, 2),
            total_cost=round(total_cost, 2),
            net_value=round(net_value, 2),
        )

    def _validate(self, price: float, shares: int) -> None:
        if price <= 0:
            raise ValueError("price must be greater than zero")
        if shares <= 0:
            raise ValueError("shares must be greater than zero")
