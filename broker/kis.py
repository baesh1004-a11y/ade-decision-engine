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
        payload = self._request_domestic_balance()
        output2 = payload.get("output2") or []
        if isinstance(output2, list) and output2:
            row = output2[0]
            for key in ("ord_psbl_cash", "dnca_tot_amt", "nass_amt"):
                if key in row:
                    return self._to_float(row[key])
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
            "raw": dict(row),
        }

    def _headers(self, tr_id: str | None = None) -> dict[str, str]:
        headers = {
            "authorization": f"Bearer {self._token()}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "content-type": "application/json; charset=utf-8",
        }
        if tr_id:
            headers["tr_id"] = tr_id
        return headers

    def _token(self) -> str:
        with self._request_lock:
            if self._access_token and time.time() < self._access_token_expires_at - 60:
                return self._access_token
            response = self._send_with_retry(
                "POST",
                "/oauth2/tokenP",
                json={"grant_type": "client_credentials", "appkey": self.config.app_key, "appsecret": self.config.app_secret},
                include_auth_headers=False,
            )
            payload = response.json()
            token = payload.get("access_token")
            if not token:
                raise BrokerError(f"KIS token response did not include access_token: {payload}")
            self._access_token = str(token)
            self._access_token_expires_at = time.time() + int(payload.get("expires_in", 86400))
            return self._access_token

    def _get(self, path: str, tr_id: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self._send_with_retry("GET", path, headers=self._headers(tr_id), params=params)
        payload = response.json()
        self._raise_for_kis_error(payload)
        return payload

    def _post(self, path: str, tr_id: str, json: dict[str, Any]) -> dict[str, Any]:
        response = self._send_with_retry("POST", path, headers=self._headers(tr_id), json=json)
        payload = response.json()
        self._raise_for_kis_error(payload)
        return payload

    def _send_with_retry(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        include_auth_headers: bool = True,
    ) -> requests.Response:
        with self._request_lock:
            url = f"{self.base_url}{path}"
            last_response: requests.Response | None = None
            for attempt in range(self.MAX_RETRIES + 1):
                self._throttle()
                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                    timeout=self.config.timeout_seconds,
                )
                last_response = response
                if not self._is_retryable_response(response):
                    self._raise_for_response(response)
                    return response
                time.sleep(min(4.0, 0.8 * (2 ** attempt)))
            assert last_response is not None
            self._raise_for_response(last_response)
            return last_response

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(self.MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        self._last_request_at = time.monotonic()

    def _is_retryable_response(self, response: requests.Response) -> bool:
        if response.status_code == 429:
            return True
        if response.status_code >= 500:
            try:
                payload = response.json()
            except Exception:
                return True
            return str(payload.get("msg_cd")) in self.RATE_LIMIT_CODES or response.status_code >= 500
        try:
            payload = response.json()
        except Exception:
            return False
        return str(payload.get("msg_cd")) in self.RATE_LIMIT_CODES

    @staticmethod
    def _raise_for_response(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise BrokerError(f"KIS HTTP {response.status_code}: {response.text[:500]}") from exc

    @staticmethod
    def _raise_for_kis_error(payload: dict[str, Any]) -> None:
        if str(payload.get("rt_cd", "0")) != "0":
            raise BrokerError(f"KIS {payload.get('msg_cd', '')}: {payload.get('msg1', '')}")

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0


def _normalize_account_parts(raw_account: str, raw_product: str) -> tuple[str, str]:
    account_text = "".join(ch for ch in str(raw_account or "").strip() if ch.isdigit())
    product_text = "".join(ch for ch in str(raw_product or "").strip() if ch.isdigit())
    if len(account_text) == 10 and not product_text:
        account_text, product_text = account_text[:8], account_text[8:]
    elif len(account_text) == 10 and product_text == "01":
        account_text = account_text[:8]
    if len(account_text) != 8:
        raise BrokerError("KIS account number must be exactly 8 digits (CANO)")
    if not product_text:
        product_text = "01"
    if len(product_text) != 2:
        raise BrokerError("KIS account product code must be exactly 2 digits (ACNT_PRDT_CD)")
    return account_text, product_text


def kis_config_from_env() -> BrokerConfig:
    if load_dotenv:
        load_dotenv()
    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    account_primary = os.getenv("KIS_ACCOUNT_NO", "").strip()
    account_legacy = os.getenv("KIS_ACCOUNT", "").strip()
    product_primary = os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "").strip()
    product_alias = os.getenv("KIS_PRODUCT_CODE", "").strip()

    # Legacy Render layout: KIS_ACCOUNT contains the 8-digit CANO and
    # KIS_ACCOUNT_NO contains the 2-digit product code.
    legacy_layout = len("".join(ch for ch in account_legacy if ch.isdigit())) == 8 and len("".join(ch for ch in account_primary if ch.isdigit())) == 2
    if legacy_layout:
        raw_account = account_legacy
        raw_product = product_primary or product_alias or account_primary
    else:
        raw_account = account_primary or account_legacy
        raw_product = product_primary or product_alias

    environment = os.getenv("KIS_ENV", "paper").strip().lower() or "paper"
    if not app_key or not app_secret or not raw_account:
        raise BrokerError("KIS_APP_KEY, KIS_APP_SECRET, and KIS_ACCOUNT_NO (or KIS_ACCOUNT) are required")
    account_no, product_code = _normalize_account_parts(raw_account, raw_product)
    return BrokerConfig(
        app_key=app_key,
        app_secret=app_secret,
        account_no=account_no,
        account_product_code=product_code,
        environment=environment,
        base_url=os.getenv("KIS_BASE_URL", "").strip() or None,
        timeout_seconds=int(float(os.getenv("KIS_TIMEOUT_SECONDS", "10"))),
    )


def kis_broker_from_env() -> KISBrokerAdapter:
    return KISBrokerAdapter(kis_config_from_env())
