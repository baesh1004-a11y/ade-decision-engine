from __future__ import annotations

import logging
import os
import time

from dashboard.kis_zero_base_bridge import load_kis_quote, submit_paper_order
from dashboard.scheduled_order_executor import run_scheduled_orders_once


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
LOGGER = logging.getLogger("scheduled-orders")


def _quote_loader(ticker: str):
    return load_kis_quote(ticker, refresh=True)


def _submitter(ticker: str, side: str, quantity: int, order_type: str, limit_price: float | None):
    try:
        result = submit_paper_order(
            ticker=ticker,
            side="BUY" if side == "매수" else "SELL",
            quantity=int(quantity),
            order_type=order_type,
            limit_price=limit_price,
        )
    except Exception as exc:
        return False, str(exc)
    if not result.accepted:
        return False, str(result.message or "KIS 주문 거절")
    return True, f"주문번호 {result.order_id or '-'}"


def main() -> None:
    interval = max(10, int(os.getenv("SCHEDULED_ORDER_POLL_SECONDS", "30")))
    require_approval = os.getenv("SCHEDULED_ORDER_REQUIRE_APPROVAL", "0").strip() in {"1", "true", "TRUE", "yes", "YES"}
    LOGGER.info("scheduled order worker started interval=%ss require_approval=%s", interval, require_approval)
    while True:
        try:
            stats = run_scheduled_orders_once(
                quote_loader=_quote_loader,
                submitter=_submitter,
                require_approval=require_approval,
            )
            if stats["triggered"] or stats["failed"]:
                LOGGER.info("scheduled order pass %s", stats)
        except Exception:
            LOGGER.exception("scheduled order pass failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
