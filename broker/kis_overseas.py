from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

from broker.base import BrokerError, BrokerOrder, BrokerPosition, OrderResult
from broker.kis import KISBrokerAdapter, kis_config_from_env


class KISOverseasStockAdapter(KISBrokerAdapter):
    """KIS overseas-stock adapter for US paper/live orders.

    KIS paper trading supports US limit orders only. Live orders remain protected by
    KIS_US_LIVE_ORDER_ENABLED=YES.
    """

    def place_us_order(self, order: BrokerOrder, exchange: str) -> OrderResult:
        order.validate()
        exchange = normalize_exchange(exchange)
        if order.market != "us":
            raise BrokerError("미국주식 주문만 지원합니다.")
        if order.order_type != "LIMIT":
            raise BrokerError("KIS 미국주식 모의투자는 지정가 주문만 지원합니다.")
        if order.limit_price is None or order.limit_price <= 0:
            raise BrokerError("미국주식 지정가를 입력해야 합니다.")
        if order.dry_run:
            return OrderResult(
                accepted=True,
                broker="kis",
                market="us",
                ticker=order.ticker,
                side=order.side,
                quantity=order.quantity,
                message="dry_run accepted; no order was sent",
                raw={"dry_run": True, "exchange": exchange},
            )
        if self.config.is_live and os.getenv("KIS_US_LIVE_ORDER_ENABLED", "NO").upper() != "YES":
            raise BrokerError("미국 실전 주문이 잠겨 있습니다. KIS_US_LIVE_ORDER_ENABLED=YES 설정이 필요합니다.")

        if self.config.is_live:
            tr_id = "TTTT1002U" if order.side == "BUY" else "TTTT1006U"
        else:
            tr_id = "VTTT1002U" if order.side == "BUY" else "VTTT1001U"

        body = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "OVRS_EXCG_CD": exchange,
            "PDNO": order.ticker.upper(),
            "ORD_QTY": str(order.quantity),
            "OVRS_ORD_UNPR": f"{float(order.limit_price):.4f}".rstrip("0").rstrip("."),
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "SLL_TYPE": "" if order.side == "BUY" else "00",
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": "00",
        }
        payload = self._post("/uapi/overseas-stock/v1/trading/order", tr_id=tr_id, json=body)
        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        order_id = output.get("ODNO") or output.get("odno")
        return OrderResult(
            accepted=payload.get("rt_cd") == "0",
            broker="kis",
            market="us",
            ticker=order.ticker.upper(),
            side=order.side,
            quantity=order.quantity,
            order_id=str(order_id) if order_id else None,
            message=str(payload.get("msg1", "")),
            raw=payload,
        )

    def get_us_buying_power(self, ticker: str, exchange: str, price: float) -> float:
        """Return USD buying power for a US limit order, failing closed on bad data."""
        params = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "OVRS_EXCG_CD": normalize_exchange(exchange),
            "OVRS_ORD_UNPR": f"{float(price):.4f}".rstrip("0").rstrip("."),
            "ITEM_CD": ticker.upper(),
        }
        tr_id = "TTTS3007R" if self.config.is_live else "VTTS3007R"
        payload = self._get(
            "/uapi/overseas-stock/v1/trading/inquire-psamount",
            tr_id=tr_id,
            params=params,
        )
        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        value = self._to_float(
            output.get("ovrs_ord_psbl_amt", output.get("frcr_ord_psbl_amt1", 0))
        )
        if payload.get("rt_cd") != "0" or value <= 0:
            raise BrokerError("미국주식 주문 가능 달러를 확인할 수 없어 매수 승인을 중단했습니다.")
        return value

    def get_us_positions(self, exchange: str = "NASD") -> list[BrokerPosition]:
        exchange = normalize_exchange(exchange)
        params = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "OVRS_EXCG_CD": exchange,
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        tr_id = "TTTS3012R" if self.config.is_live else "VTTS3012R"
        payload = self._get(
            "/uapi/overseas-stock/v1/trading/inquire-balance",
            tr_id=tr_id,
            params=params,
        )
        rows = payload.get("output1") or payload.get("output2") or []
        if isinstance(rows, dict):
            rows = [rows]
        positions: list[BrokerPosition] = []
        for row in rows if isinstance(rows, list) else []:
            qty = int(self._to_float(row.get("ovrs_cblc_qty", row.get("hldg_qty", 0))))
            if qty <= 0:
                continue
            avg_price = self._to_float(row.get("pchs_avg_pric", row.get("avg_pric", 0)))
            current_price = self._to_float(row.get("now_pric2", row.get("ovrs_now_pric1", row.get("prpr", 0))))
            evaluation = self._to_float(row.get("ovrs_stck_evlu_amt", row.get("evlu_amt", 0)))
            pnl = self._to_float(row.get("frcr_evlu_pfls_amt", row.get("evlu_pfls_amt", 0)))
            pnl_rate = self._to_float(row.get("evlu_pfls_rt", row.get("evlu_pfls_rate", 0)))
            positions.append(
                BrokerPosition(
                    market="us",
                    ticker=str(row.get("ovrs_pdno", row.get("pdno", ""))).upper(),
                    name=str(row.get("ovrs_item_name", row.get("prdt_name", ""))),
                    quantity=qty,
                    average_price=avg_price,
                    current_price=current_price,
                    evaluation_amount=evaluation,
                    pnl=pnl,
                    pnl_rate=pnl_rate,
                )
            )
        return positions

    def get_us_executions(self, days: int = 7) -> list[dict[str, object]]:
        end = date.today()
        start = end - timedelta(days=max(1, int(days)))
        paper = not self.config.is_live
        params = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "PDNO": "" if paper else "%",
            "ORD_STRT_DT": start.strftime("%Y%m%d"),
            "ORD_END_DT": end.strftime("%Y%m%d"),
            "SLL_BUY_DVSN": "00",
            "CCLD_NCCS_DVSN": "00",
            "OVRS_EXCG_CD": "" if paper else "%",
            "SORT_SQN": "DS",
            "ORD_DT": "",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "CTX_AREA_NK200": "",
            "CTX_AREA_FK200": "",
        }
        tr_id = "TTTS3035R" if self.config.is_live else "VTTS3035R"
        payload = self._get(
            "/uapi/overseas-stock/v1/trading/inquire-ccnl",
            tr_id=tr_id,
            params=params,
        )
        rows = payload.get("output") or []
        if isinstance(rows, dict):
            rows = [rows]
        return [self._normalize_execution(row) for row in rows if isinstance(row, dict)]

    @classmethod
    def _normalize_execution(cls, row: dict[str, Any]) -> dict[str, object]:
        ordered = int(cls._to_float(row.get("ft_ord_qty", row.get("ord_qty", 0))))
        filled = int(cls._to_float(row.get("ft_ccld_qty", row.get("tot_ccld_qty", row.get("ccld_qty", 0)))))
        side_name = str(row.get("sll_buy_dvsn_cd_name", row.get("sll_buy_dvsn_name", "")))
        side_code = str(row.get("sll_buy_dvsn_cd", row.get("sll_buy_dvsn", "")))
        side = "BUY" if side_code == "02" or "매수" in side_name else "SELL" if side_code == "01" or "매도" in side_name else ""
        status = "FILLED" if ordered > 0 and filled >= ordered else "PARTIALLY_FILLED" if filled > 0 else "SENT"
        return {
            "order_id": str(row.get("odno", row.get("ODNO", ""))),
            "ticker": str(row.get("pdno", row.get("ovrs_pdno", ""))).upper(),
            "name": str(row.get("prdt_name", row.get("ovrs_item_name", ""))),
            "exchange": str(row.get("ovrs_excg_cd", "")),
            "side": side,
            "ordered_quantity": ordered,
            "filled_quantity": filled,
            "filled_price": cls._to_float(row.get("ft_ccld_unpr3", row.get("avg_ccld_prc", row.get("ccld_unpr", 0)))),
            "status": status,
            "order_date": str(row.get("ord_dt", "")),
            "order_time": str(row.get("ord_tmd", "")),
            "raw": row,
        }


def normalize_exchange(value: str) -> str:
    text = value.strip().upper()
    aliases = {
        "NASDAQ": "NASD",
        "NAS": "NASD",
        "NASD": "NASD",
        "NYSE": "NYSE",
        "NEW YORK": "NYSE",
        "AMEX": "AMEX",
    }
    if text not in aliases:
        raise BrokerError(f"지원하지 않는 미국 거래소입니다: {value}")
    return aliases[text]


def kis_overseas_broker_from_env() -> KISOverseasStockAdapter:
    return KISOverseasStockAdapter(kis_config_from_env())
