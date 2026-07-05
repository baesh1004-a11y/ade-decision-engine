from __future__ import annotations

import os
import time
from typing import Any

import requests

from broker.base import BrokerConfig, BrokerError, BrokerOrder, BrokerPosition, OrderResult

try:  # python-dotenv is optional for tests and production secret managers.
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


class KISBrokerAdapter:
    """Korea Investment Securities REST broker adapter.

    Scope v1:
    - OAuth token issuance
    - domestic stock cash/position normalization skeleton
    - guarded paper/live order entry interface
    - KIS API rate-limit guard and retry handling

    Secrets must be injected from environment variables or a secret manager.
    Never hard-code APP_KEY, APP_SECRET, account number, or token in GitHub.
    """

    PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
    LIVE_BASE_URL = "https://openapi.koreainvestment.com:9443"

    MIN_REQUEST_INTERVAL_SECONDS = 0.75
    MAX_RETRIES = 3
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

    def get_cash(self) -> float:
        payload = self._request_domestic_balance()
        # KIS response fields differ by product and endpoint version. Keep parsing defensive.
        output2 = payload.get("output2") or []
        if isinstance(output2, list) and output2:
            row = output2[0]
            for key in ("dnca_tot_amt", "ord_psbl_cash", "nass_amt"):
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
            positions.append(
                BrokerPosition(
                    market="kr",
                    ticker=str(row.get("pdno", "")),
                    name=str(row.get("prdt_name", "")),
                    quantity=quantity,
                    average_price=self._to_float(row.get("pchs_avg_pric", 0)),
                    current_price=self._to_float(row.get("prpr", 0)),
                    evaluation_amount=self._to_float(row.get("evlu_amt", 0)),
                    pnl=self._to_float(row.get("evlu_pfls_amt", 0)),
                    pnl_rate=self._to_float(row.get("evlu_pfls_rt", 0)),
                )
            )
        return positions

    def place_order(self, order: BrokerOrder) -> OrderResult:
        order.validate()
        if order.market != "kr":
            raise BrokerError("KISBrokerAdapter v1 supports Korean domestic stocks first")
        if order.dry_run:
            return OrderResult(
                accepted=True,
                broker="kis",
                market=order.market,
                ticker=order.ticker,
                side=order.side,
                quantity=order.quantity,
                message="dry_run accepted; no order was sent to KIS",
                raw={"dry_run": True},
            )
        if self.config.is_live:
            raise BrokerError("Live KIS orders are intentionally blocked in v1. Use paper trading first.")

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

    def _request_domestic_balance(self) -> dict[str, Any]:
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
        tr_id = "VTTC8434R" if not self.config.is_live else "TTTC8434R"
        payload = self._get("/uapi/domestic-stock/v1/trading/inquire-balance", tr_id=tr_id, params=params)
        self._last_balance_payload = payload
        self._last_balance_at = time.time()
        return payload

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
        if self._access_token and time.time() < self._access_token_expires_at - 60:
            return self._access_token
        body = {
            "grant_type": "client_credentials",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
        }
        response = self._send_with_retry(
            "POST",
            "/oauth2/tokenP",
            json=body,
            include_auth_headers=False,
        )
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise BrokerError(f"KIS token response did not include access_token: {payload}")
        self._access_token = str(token)
        expires_in = int(payload.get("expires_in", 24 * 60 * 60))
        self._access_token_expires_at = time.time() + expires_in
        return self._access_token

    def _get(self, path: str, tr_id: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self._send_with_retry(
            "GET",
            path,
            headers=self._headers(tr_id),
            params=params,
        )
        payload = response.json()
        self._raise_for_kis_error(payload)
        return payload

    def _post(self, path: str, tr_id: str, json: dict[str, Any]) -> dict[str, Any]:
        response = self._send_with_retry(
            "POST",
            path,
            headers=self._headers(tr_id),
            json=json,
        )
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

            wait_seconds = min(4.0, 0.8 * (2**attempt))
            time.sleep(wait_seconds)

        assert last_response is not None
        self._raise_for_response(last_response)
        return last_response

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(self.MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        self._last_request_at = time.time()

    def _is_retryable_response(self, response: requests.Response) -> bool:
        if response.status_code in {429, 500, 502, 503, 504}:
            try:
                payload = response.json()
            except ValueError:
                return response.status_code in {429, 502, 503, 504}
            if payload.get("msg_cd") in self.RATE_LIMIT_CODES:
                return True
            if "초당 거래건수" in str(payload.get("msg1", "")):
                return True
        return False

    @staticmethod
    def _raise_for_response(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise BrokerError(f"KIS HTTP error: {response.status_code} {response.text}") from exc

    @staticmethod
    def _raise_for_kis_error(payload: dict[str, Any]) -> None:
        if payload.get("rt_cd") not in {None, "0"}:
            raise BrokerError(f"KIS API error: {payload.get('msg_cd')} {payload.get('msg1')}")

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0


def load_kis_env() -> None:
    """Load .env when python-dotenv is available.

    The function is intentionally safe when python-dotenv is not installed so
    production deployments can rely on native environment variables or secret
    managers without importing dotenv.
    """

    if load_dotenv is not None:
        load_dotenv()


def kis_config_from_env(prefix: str = "KIS") -> BrokerConfig:
    """Build BrokerConfig from environment variables.

    Required variables:
    - KIS_APP_KEY
    - KIS_APP_SECRET
    - KIS_ACCOUNT or KIS_ACCOUNT_NO
    - KIS_PRODUCT_CODE or KIS_ACCOUNT_PRODUCT_CODE

    Optional variables:
    - KIS_ENV=paper|live
    - KIS_BASE_URL
    - KIS_TIMEOUT_SECONDS
    """

    load_kis_env()
    app_key = os.getenv(f"{prefix}_APP_KEY")
    app_secret = os.getenv(f"{prefix}_APP_SECRET")
    account_no = os.getenv(f"{prefix}_ACCOUNT") or os.getenv(f"{prefix}_ACCOUNT_NO")
    product_code = os.getenv(f"{prefix}_PRODUCT_CODE") or os.getenv(f"{prefix}_ACCOUNT_PRODUCT_CODE") or "01"
    environment = os.getenv(f"{prefix}_ENV", "paper")
    base_url = os.getenv(f"{prefix}_BASE_URL")
    timeout_seconds = int(os.getenv(f"{prefix}_TIMEOUT_SECONDS", "10"))

    missing = []
    if not app_key:
        missing.append(f"{prefix}_APP_KEY")
    if not app_secret:
        missing.append(f"{prefix}_APP_SECRET")
    if not account_no:
        missing.append(f"{prefix}_ACCOUNT or {prefix}_ACCOUNT_NO")
    if missing:
        raise BrokerError("Missing KIS environment variables: " + ", ".join(missing))

    return BrokerConfig(
        app_key=app_key,
        app_secret=app_secret,
        account_no=account_no,
        account_product_code=product_code,
        environment=environment,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def kis_broker_from_env(prefix: str = "KIS", session: requests.Session | None = None) -> KISBrokerAdapter:
    """Create a KISBrokerAdapter from .env or process environment."""

    return KISBrokerAdapter(config=kis_config_from_env(prefix=prefix), session=session)
