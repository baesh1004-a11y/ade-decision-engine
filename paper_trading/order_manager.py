from __future__ import annotations

from pathlib import Path
from typing import Iterable

from broker.base import BrokerOrder
from datahub.repository import PriceRepository
from paper_trading.models import PaperOrderExecution, PaperOrderPlan


class PaperOrderManager:
    """Convert ADE recommendations into paper-trading buy orders.

    Paper rule:
    - buy every recommended stock,
    - equal budget per stock,
    - market order,
    - skip stocks already held unless explicitly allowed,
    - sell rules are intentionally not implemented yet.
    """

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.price_repo = PriceRepository(db_path)
        self.last_skipped_held: list[str] = []

    def close(self) -> None:
        self.price_repo.close()

    def build_buy_plans(
        self,
        recommendations: Iterable[object],
        budget_per_stock: int = 1_000_000,
        held_position_keys: set[str] | None = None,
        allow_rebuy: bool = False,
    ) -> list[PaperOrderPlan]:
        plans: list[PaperOrderPlan] = []
        seen: set[str] = set()
        held = {str(key).lower() for key in (held_position_keys or set())}
        self.last_skipped_held = []

        for item in recommendations:
            market = str(getattr(item, "market", "kr")).lower()
            ticker = str(getattr(item, "ticker", ""))
            key = f"{market}:{ticker}".lower()
            if not ticker or key in seen:
                continue
            seen.add(key)

            if not allow_rebuy and key in held:
                self.last_skipped_held.append(key)
                continue

            price = self._latest_close(market, ticker)
            if price <= 0:
                continue
            quantity = int(budget_per_stock // price)
            if quantity <= 0:
                continue
            plans.append(
                PaperOrderPlan(
                    market=market,
                    ticker=ticker,
                    name=getattr(item, "name", None),
                    side="BUY",
                    budget=budget_per_stock,
                    reference_price=round(price, 4),
                    quantity=quantity,
                    estimated_amount=int(quantity * price),
                    top1_event_id=str(getattr(item, "matched_event_id", "") or ""),
                    weekly_similarity=_float_or_none(getattr(item, "weekly_similarity", None)),
                    sto_similarity=_float_or_none(getattr(item, "sto_similarity", None)),
                    final_similarity=_float_or_none(getattr(item, "final_similarity", None)),
                )
            )
        return plans

    def execute(self, broker: object, plans: Iterable[PaperOrderPlan], dry_run: bool = True) -> list[PaperOrderExecution]:
        executions: list[PaperOrderExecution] = []
        for plan in plans:
            result = broker.place_order(
                BrokerOrder(
                    market=plan.market,
                    ticker=plan.ticker,
                    side=plan.side,
                    quantity=plan.quantity,
                    order_type="MARKET",
                    dry_run=dry_run,
                )
            )
            executions.append(
                PaperOrderExecution(
                    plan=plan,
                    accepted=bool(result.accepted),
                    order_id=result.order_id,
                    message=result.message,
                    raw=result.raw,
                )
            )
        return executions

    def _latest_close(self, market: str, ticker: str) -> float:
        df = self.price_repo.fetch_dataframe(market, ticker, source="fdr")
        if df.empty:
            df = self.price_repo.fetch_dataframe(market, ticker)
        if df.empty or "Close" not in df.columns:
            return 0.0
        try:
            return float(df.iloc[-1]["Close"])
        except Exception:
            return 0.0


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except Exception:
        return None
