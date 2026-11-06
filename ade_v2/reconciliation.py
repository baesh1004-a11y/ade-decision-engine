"""Fail-closed broker fill reconciliation. Does not submit orders."""
from dataclasses import dataclass, field
from math import isfinite


@dataclass(frozen=True)
class ConfirmedFill:
    fill_id: str
    order_id: str
    ticker: str
    side: str
    quantity: int
    price: float


@dataclass
class FillReconciler:
    """Deduplicate verified partial fills. Persist seen IDs before production."""
    seen: dict[str, ConfirmedFill] = field(default_factory=dict)
    filled_qty: dict[str, int] = field(default_factory=dict)
    order_identity: dict[str, tuple[str, str, int]] = field(default_factory=dict)

    def accept(self, fill: ConfirmedFill, *, expected_order_id: str,
               expected_ticker: str, expected_side: str,
               ordered_quantity: int) -> bool:
        if not fill.fill_id or not fill.order_id or not fill.ticker:
            raise ValueError("Missing fill identity")
        if fill.order_id != expected_order_id or fill.ticker != expected_ticker or fill.side != expected_side:
            raise ValueError("Fill does not match order")
        if fill.side not in ("BUY", "SELL") or type(fill.quantity) is not int or fill.quantity <= 0:
            raise ValueError("Invalid fill side or quantity")
        if not isfinite(fill.price) or fill.price <= 0:
            raise ValueError("Invalid fill price")
        if type(ordered_quantity) is not int or ordered_quantity <= 0:
            raise ValueError("Invalid ordered quantity")
        identity = (expected_ticker, expected_side, ordered_quantity)
        if fill.order_id in self.order_identity and self.order_identity[fill.order_id] != identity:
            raise ValueError("Conflicting order identity across partial fills")
        if fill.fill_id in self.seen:
            if self.seen[fill.fill_id] != fill:
                raise ValueError("Conflicting duplicate fill")
            return False
        current = self.filled_qty.get(fill.order_id, 0)
        if current + fill.quantity > ordered_quantity:
            raise ValueError("Overfill")
        self.order_identity[fill.order_id] = identity
        self.seen[fill.fill_id] = fill
        self.filled_qty[fill.order_id] = current + fill.quantity
        return True
