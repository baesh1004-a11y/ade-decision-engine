from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


class BrokerError(RuntimeError):
    """Raised when a broker adapter cannot complete a request."""


@dataclass(frozen=True)
class BrokerConfig:
    app_key: str
    app_secret: str
    account_no: str
    account_product_code: str = "01"
    environment: str = "paper"  # paper | live
    base_url: str | None = None
    timeout_seconds: int = 10

    @property
    def is_live(self) -> bool:
        return self.environment.lower() == "live"

    @property
    def account_id(self) -> str:
        return f"{self.account_no}-{self.account_product_code}"


@dataclass(frozen=True)
class BrokerPosition:
    market: str
    ticker: str
    name: str
    quantity: int
    average_price: float
    current_price: float
    evaluation_amount: float
    pnl: float
    pnl_rate: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BrokerOrder:
    market: str
    ticker: str
    side: str  # BUY | SELL
    quantity: int
    order_type: str = "MARKET"  # MARKET | LIMIT
    limit_price: float | None = None
    dry_run: bool = True

    def validate(self) -> None:
        if self.side not in {"BUY", "SELL"}:
            raise BrokerError(f"Unsupported order side: {self.side}")
        if self.quantity <= 0:
            raise BrokerError("Order quantity must be positive")
        if self.order_type not in {"MARKET", "LIMIT"}:
            raise BrokerError(f"Unsupported order type: {self.order_type}")
        if self.order_type == "LIMIT" and (self.limit_price is None or self.limit_price <= 0):
            raise BrokerError("LIMIT order requires a positive limit_price")


@dataclass(frozen=True)
class OrderResult:
    accepted: bool
    broker: str
    market: str
    ticker: str
    side: str
    quantity: int
    order_id: str | None = None
    message: str = ""
    raw: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class BrokerAdapter(Protocol):
    """Execution/account adapter interface used by ADE."""

    def get_cash(self) -> float:
        ...

    def get_positions(self) -> list[BrokerPosition]:
        ...

    def place_order(self, order: BrokerOrder) -> OrderResult:
        ...
