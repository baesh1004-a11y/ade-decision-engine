from __future__ import annotations

import os
import threading
import time
from typing import Any

import requests

from broker.base import BrokerConfig, BrokerError, BrokerOrder, BrokerPosition, OrderResult

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


class KISBrokerAdapter:
    """Korea Investment Securities REST broker adapter for guarded paper trading."""

    PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
    LIVE_BASE_URL = "https://openapi.koreainvestment.com:9443"
    MIN_REQUEST_INTERVAL_SECONDS = 0.75
    MAX_RETRIES = 3
    MAX_ORDER_PAGES = 20
    BALANCE_CACHE_SECONDS = 2.0
    RATE_LIMIT_CODES = {"EGW00201"}

    def __init__(self, config: BrokerConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.base_url = config.base_url or (self.LIVE_BASE_URL if config.is_live else self.PAPER_BASE_URL)
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0
        self._last_request_at = 0.0
        self._last_balance_payload: dict[str, Any] | None = None
        self._last_balance_at = 0.0
        self._request_lock = threading.RLock()

    def get_cash(self) -> float:
        """Return settled deposit cash for account asset calculation.

        KIS `ord_psbl_cash` is orderable cash and can include buying-power semantics,
        so adding it to stock evaluation can overstate total account assets.
        For portfolio assets, prefer the actual deposit balance (`dnca_tot_amt`).
        `nass_amt` is net asset value, not cash, and must never be added to holdings.
        """
        payload = self._request_domestic_balance()
        output2 = payload.get("output2") or []
        if isinstance(output2, list) and output2:
            row = output2[0]
            if row.get("dnca_tot_amt") not in (None, ""):
                return self._to_float(row.get("dnca_tot_amt"))
            if row.get("prvs_rcdl_excc_amt") not in (None, ""):
                return self._to_float(row.get("prvs_rcdl_excc_amt"))
        return 0.0

    def get_positions(self) -> list[BrokerPosition]:
        payload = self._request_domestic_balance()
        rows = payload.get("output1") or []
        positions: list[BrokerPosition] = []
        if not isinstance(rows, list):
            return positions
        for row in rows:
            quantity = int(self._to_float(row.get("hldg_qty", 0)))
            if quantity <= 0:
                continue
            positions.append(BrokerPosition(
                market="kr",
                ticker=str(row.get("pdno", "")),
                name=str(row.get("prdt_name", "")),
                quantity=quantity,
                average_price=self._to_float(row.get("pchs_avg_pric", 0)),
                current_price=self._to_float(row.get("prpr", 0)),
                evaluation_amount=self._to_float(row.get("evlu_amt", 0)),
                pnl=self._to_float(row.get("evlu_pfls_amt", 0)),
                pnl_rate=self._to_float(row.get("evlu_pfls_rt", 0)),
            ))
        return positions

    def get_quote(self, ticker: str) -> dict[str, Any]:
        payload = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(ticker).zfill(6)},
        )
        row = payload.get("output") or {}
        return {
            "ticker": str(ticker).zfill(6),
            "price": self._to_float(row.get("stck_prpr")),
            "change": self._to_float(row.get("prdy_vrss")),
            "change_rate": self._to_float(row.get("prdy_ctrt")),
            "open": self._to_float(row.get("stck_oprc")),
            "high": self._to_float(row.get("stck_hgpr")),
            "low": self._to_float(row.get("stck_lwpr")),
            "volume": int(self._to_float(row.get("acml_vol"))),
            "turnover": self._to_float(row.get("acml_tr_pbmn")),
            "upper_limit": self._to_float(row.get("stck_mxpr")),
            "lower_limit": self._to_float(row.get("stck_llam")),
            "market_cap": self._to_float(row.get("hts_avls")),
            "per": self._to_float(row.get("per")),
            "pbr": self._to_float(row.get("pbr")),
            "raw": row,
        }

    def get_index_quote(self, index_code: str) -> dict[str, Any]:
        normalized = str(index_code).strip()
        payload = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-index-price",
            tr_id="FHPUP02100000",
            params={"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": normalized},
        )
        row = payload.get("output") or {}
        value = self._to_float(row.get("bstp_nmix_prpr"))
        change = self._to_float(row.get("bstp_nmix_prdy_vrss"))
        change_rate = self._to_float(row.get("bstp_nmix_prdy_ctrt"))
        if value <= 0:
            raise BrokerError(f"KIS index quote is empty for {normalized}")
        return {
            "code": normalized,
            "value": value,
            "change": change,
            "change_rate": change_rate,
            "updated_at": time.time(),
            "raw": row,
        }

    def get_orderable(self, ticker: str, price: float, order_type: str = "LIMIT") -> dict[str, Any]:
        ord_dvsn = "01" if order_type.upper() == "MARKET" else "00"
        params = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "PDNO": str(ticker).zfill(6),
            "ORD_UNPR": "0" if ord_dvsn == "01" else str(int(price)),
            "ORD_DVSN": ord_dvsn,
            "CMA_EVLU_AMT_ICLD_YN": "N",
            "OVRS_ICLD_YN": "N",
        }
        payload = self._get(
            "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
            tr_id="VTTC8908R" if not self.config.is_live else "TTTC8908R",
            params=params,
        )
        row = payload.get("output") or {}
        return {
            "orderable_cash": self._to_float(row.get("ord_psbl_cash")),
            "orderable_quantity": int(self._to_float(row.get("max_buy_qty"))),
            "cash_orderable_quantity": int(self._to_float(row.get("nrcvb_buy_qty"))),
            "raw": row,
        }

    def get_daily_orders(self, executed_only: bool = False) -> list[dict[str, Any]]:
        params = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "INQR_STRT_DT": time.strftime("%Y%m%d"),
            "INQR_END_DT": time.strftime("%Y%m%d"),
            "SLL_BUY_DVSN_CD": "00",
            "INQR_DVSN": "00",
            "PDNO": "",
            "CCLD_DVSN": "01" if executed_only else "00",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        path = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        tr_id = "VTTC8001R" if not self.config.is_live else "TTTC8001R"
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for _ in range(self.MAX_ORDER_PAGES):
            payload = self._get(path, tr_id=tr_id, params=params)
            rows = payload.get("output1") or []
            if not isinstance(rows, list):
                raise BrokerError("KIS daily-order response output1 is not a list")
            for raw in rows:
                row = self._normalize_daily_order(raw)
                dedupe_key = (str(row.get("order_id") or ""), str(row.get("ticker") or ""), str(row.get("order_time") or ""))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                normalized.append(row)
            next_fk = str(payload.get("ctx_area_fk100") or payload.get("CTX_AREA_FK100") or "").strip()
            next_nk = str(payload.get("ctx_area_nk100") or payload.get("CTX_AREA_NK100") or "").strip()
            if not next_fk and not next_nk:
                break
            if next_fk == params["CTX_AREA_FK100"] and next_nk == params["CTX_AREA_NK100"]:
                break
            params["CTX_AREA_FK100"] = next_fk
            params["CTX_AREA_NK100"] = next_nk
        return normalized

    def get_pending_orders(self) -> list[dict[str, Any]]:
        return [row for row in self.get_daily_orders(executed_only=False) if int(row.get("remaining_quantity") or 0) > 0]

    def place_order(self, order: BrokerOrder) -> OrderResult:
        order.validate()
        if order.market != "kr":
            raise BrokerError("KISBrokerAdapter supports Korean domestic stocks first")
        if order.dry_run:
            return OrderResult(True, "kis", order.market, order.ticker, order.side, order.quantity,
                               message="dry_run accepted; no order was sent to KIS", raw={"dry_run": True})
        if self.config.is_live:
            raise BrokerError("Live KIS orders are intentionally blocked. Use paper trading.")
        tr_id = "VTTC0802U" if order.side == "BUY" else "VTTC0801U"
        ord_dvsn = "01" if order.order_type == "MARKET" else "00"
        price = "0" if order.order_type == "MARKET" else str(int(order.limit_price or 0))
        body = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "PDNO": str(order.ticker).zfill(6),
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(order.quantity),
            "ORD_UNPR": price,
        }
        payload = self._post("/uapi/domestic-stock/v1/trading/order-cash", tr_id=tr_id, json=body)
        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        return OrderResult(
            payload.get("rt_cd") == "0",
            "kis",
            order.market,
            order.ticker,
            order.side,
            order.quantity,
            str(output.get("ODNO")) if output else None,
            str(payload.get("msg1", "")),
            payload,
        )

    def revise_or_cancel_order(
        self,
        order_id: str,
        quantity: int,
        *,
        price: float = 0,
        cancel: bool = False,
        total_quantity: bool = True,
        organization_no: str = "",
    ) -> dict[str, Any]:
        if self.config.is_live:
            raise BrokerError("Live KIS order revisions are intentionally blocked.")
        body = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "KRX_FWDG_ORD_ORGNO": str(organization_no or ""),
            "ORGN_ODNO": str(order_id),
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02" if cancel else "01",
            "ORD_QTY": str(quantity),
            "ORD_UNPR": "0" if cancel else str(int(price)),
            "QTY_ALL_ORD_YN": "Y" if total_quantity else "N",
        }
        payload = self._post(
            "/uapi/domestic-stock/v1/trading/order-rvsecncl",
            tr_id="VTTC0803U",
            json=body,
        )
        if str(payload.get("rt_cd") or "") != "0":
            raise BrokerError(str(payload.get("msg1") or "KIS order revision/cancel rejected"))
        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        return {
            "accepted": True,
            "action": "cancel" if cancel else "revise",
            "order_id": str(output.get("ODNO") or output.get("odno") or order_id),
            "message": str(payload.get("msg1") or ""),
            "raw": payload,
        }

    def _request_domestic_balance(self) -> dict[str, Any]:
        with self._request_lock:
            now = time.time()
            if self._last_balance_payload is not None and now - self._last_balance_at < self.BALANCE_CACHE_SECONDS:
                return self._last_balance_payload
            params = {
                "CANO": self.config.account_no,
                "ACNT_PRDT_CD": self.config.account_product_code,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            }
            payload = self._get(
                "/uapi/domestic-stock/v1/trading/inquire-balance",
                tr_id="VTTC8434R" if not self.config.is_live else "TTTC8434R",
                params=params,
            )
            self._last_balance_payload = payload
            self._last_balance_at = time.time()
            return payload

    @staticmethod
    def _normalize_daily_order(row: dict[str, Any]) -> dict[str, Any]:
        def pick(*keys: str) -> Any:
            for key in keys:
                if row.get(key) not in (None, ""):
                    return row.get(key)
            return ""

        def number(*keys: str) -> float:
            value = pick(*keys)
            try:
                return float(str(value).replace(",", ""))
            except (TypeError, ValueError):
                return 0.0

        order_quantity = int(number("ord_qty", "ORD_QTY"))
        executed_quantity = int(number("tot_ccld_qty", "TOT_CCLD_QTY"))
        remaining_quantity = int(number("rmn_qty", "RMN_QTY"))
        if remaining_quantity <= 0 and order_quantity >= executed_quantity:
            remaining_quantity = order_quantity - executed_quantity
        executed_price = number("avg_prvs", "AVG_PRVS", "avg_pric", "AVG_PRIC", "avg_ccld_pric", "AVG_CCLD_PRIC")
        if executed_price <= 0 and executed_quantity > 0:
            total_executed_amount = number("tot_ccld_amt", "TOT_CCLD_AMT")
            if total_executed_amount > 0:
                executed_price = total_executed_amount / executed_quantity
        return {
            "order_id": str(pick("odno", "ODNO")),
            "organization_no": str(pick("ord_gno_brno", "ORD_GNO_BRNO", "krx_fwdg_ord_orgno", "KRX_FWDG_ORD_ORGNO")),
            "ticker": str(pick("pdno", "PDNO")),
            "name": str(pick("prdt_name", "PRDT_NAME")),
            "side": str(pick("sll_buy_dvsn_cd_name", "SLL_BUY_DVSN_CD_NAME")),
            "order_quantity": order_quantity,
            "executed_quantity": executed_quantity,
            "remaining_quantity": remaining_quantity,
            "order_price": number("ord_unpr", "ORD_UNPR"),
            "executed_price": executed_price,
            "order_time": str(pick("ord_tmd", "ORD_TMD")),
            "raw": row,
        }

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(str(value or 0).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0


def kis_config_from_env() -> BrokerConfig:
    if load_dotenv is not None:
        load_dotenv()
    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    account_no = (os.getenv("KIS_ACCOUNT_NO") or os.getenv("KIS_ACCOUNT") or "").strip()
    account_product_code = (os.getenv("KIS_ACCOUNT_PRODUCT_CODE") or os.getenv("KIS_PRODUCT_CODE") or "01").strip()
    environment = os.getenv("KIS_ENV", "paper").strip().lower() or "paper"
    if not app_key or not app_secret or not account_no:
        raise BrokerError("KIS_APP_KEY, KIS_APP_SECRET, and KIS_ACCOUNT_NO/KIS_ACCOUNT are required")
    return BrokerConfig(
        app_key=app_key,
        app_secret=app_secret,
        account_no=account_no.replace("-", ""),
        account_product_code=account_product_code,
        environment=environment,
    )


def kis_broker_from_env() -> KISBrokerAdapter:
    return KISBrokerAdapter(kis_config_from_env())
