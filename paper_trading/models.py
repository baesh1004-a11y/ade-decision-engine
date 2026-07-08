from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PaperOrderPlan:
    market: str
    ticker: str
    name: str | None
    side: str
    budget: int
    reference_price: float
    quantity: int
    estimated_amount: int
    top1_event_id: str | None
    weekly_similarity: float | None
    sto_similarity: float | None
    final_similarity: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PaperOrderExecution:
    plan: PaperOrderPlan
    accepted: bool
    order_id: str | None
    message: str
    raw: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        data = self.plan.to_dict()
        data.update(
            {
                "accepted": self.accepted,
                "order_id": self.order_id,
                "message": self.message,
                "raw": self.raw,
            }
        )
        return data
