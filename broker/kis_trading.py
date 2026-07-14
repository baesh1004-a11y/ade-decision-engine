from __future__ import annotations

import os
from datetime import date
from typing import Any

from broker.base import BrokerError, BrokerOrder, OrderResult
from broker.kis import KISBrokerAdapter, kis_config_from_env


class KISTradingAdapter(KISBrokerAdapter):
    """KIS domestic-stock trading extension with an explicit live-order gate."""

    def place_order(self, order: BrokerOrder) -> OrderResult:
        order.validate()
        if order.market != "kr":
            raise BrokerError("국내주식 주문만 지원합니다.")
        if order.dry_run:
            return super().place_order(order)

        if self.config.is_live and os.getenv("KIS_LIVE_ORDER_ENABLED", "NO").upper() != "YES":
            raise BrokerError("실전 주문이 잠겨 있습니다. KIS_LIVE_ORDER_ENABLED=YES 설정이 필요합니다.")

        if self.config.is_live:
            tr_id = "TTTC0802U" if order.side == "BUY" else "TTTC0801U"
        else:
            tr_id = "VTTC0802U" if order.side == "BUY" else "VTTC0801U"

        ord_dvsn = "01" if order.order_type == "MARKET" else "00"
        price = "0" if order.order_type == "MARKET" else str(int(order.limit_price or 0))
        body = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "PDNO": order.ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(order.quantity),
            "ORD_UNPR": price,
        }
        payload = self._post("/uapi/domestic-stock/v1/trading/order-cash", tr_id=tr_id, json=body)
        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        return OrderResult(
            accepted=payload.get("rt_cd") == "0",
            broker="kis",
            market=order.market,
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            order_id=str(output.get("ODNO")) if output else None,
            message=str(payload.get("msg1", "")),
            raw=payload,
        )

    def get_order_executions(self) -> list[dict[str, object]]:
        today = date.today().strftime("%Y%m%d")
        params = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "INQR_STRT_DT": today,
            "INQR_END_DT": today,
            "SLL_BUY_DVSN_CD": "00",
            "INQR_DVSN": "00",
            "PDNO": "",
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        tr_id = "TTTC8001R" if self.config.is_live else "VTTC8001R"
        payload = self._get(
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            tr_id=tr_id,
            params=params,
        )
        rows = payload.get("output1") or []
        if not isinstance(rows, list):
            return []
        return [self._normalize_execution(row) for row in rows]

    @staticmethod
    def _normalize_execution(row: dict[str, Any]) -> dict[str, object]:
        ordered = int(KISBrokerAdapter._to_float(row.get("ord_qty", 0)))
        filled = int(KISBrokerAdapter._to_float(row.get("tot_ccld_qty", row.get("ccld_qty", 0))))
        side_code = str(row.get("sll_buy_dvsn_cd", ""))
        side_name = str(row.get("sll_buy_dvsn_cd_name", ""))
        side = "BUY" if side_code == "02" or "매수" in side_name else "SELL" if side_code == "01" or "매도" in side_name else ""
        if ordered > 0 and filled >= ordered:
            status = "FILLED"
        elif filled > 0:
            status = "PARTIALLY_FILLED"
        else:
            status = "SENT"
        return {
            "order_id": str(row.get("odno", row.get("ODNO", ""))),
            "ticker": str(row.get("pdno", "")),
            "name": str(row.get("prdt_name", "")),
            "side": side,
            "ordered_quantity": ordered,
            "filled_quantity": filled,
            "filled_price": KISBrokerAdapter._to_float(row.get("avg_prvs", row.get("avg_ccld_prc", 0))),
            "status": status,
            "order_time": str(row.get("ord_tmd", "")),
            "raw": row,
        }


def kis_trading_broker_from_env() -> KISTradingAdapter:
    return KISTradingAdapter(kis_config_from_env())
