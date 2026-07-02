from __future__ import annotations

import time
from typing import Any

import requests

from broker.base import BrokerConfig, BrokerError, BrokerOrder, BrokerPosition, OrderResult


class KISBrokerAdapter:
    """Korea Investment Securities REST broker adapter.

    Scope v1:
    - OAuth token issuance
    - domestic stock cash/position normalization skeleton
    - guarded paper/live order entry interface

    Secrets must be injected from environment variables or a secret manager.
    Never hard-code APP_KEY, APP_SECRET, account number, or token in GitHub.
    """

    PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
    LIVE_BASE_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(self, config: BrokerConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.base_url = config.base_url or (self.LIVE_BASE_URL if config.is_live else self.PAPER_BASE_URL)
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0

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
        return self._get("/uapi/domestic-stock/v1/trading/inquire-balance", tr_id=tr_id, params=params)

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
        response = self.session.post(
            f"{self.base_url}/oauth2/tokenP",
            json=body,
            timeout=self.config.timeout_seconds,
        )
        self._raise_for_response(response)
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise BrokerError(f"KIS token response did not include access_token: {payload}")
        self._access_token = str(token)
        expires_in = int(payload.get("expires_in", 24 * 60 * 60))
        self._access_token_expires_at = time.time() + expires_in
        return self._access_token

    def _get(self, path: str, tr_id: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}{path}",
            headers=self._headers(tr_id),
            params=params,
            timeout=self.config.timeout_seconds,
        )
        self._raise_for_response(response)
        payload = response.json()
        self._raise_for_kis_error(payload)
        return payload

    def _post(self, path: str, tr_id: str, json: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}{path}",
            headers=self._headers(tr_id),
            json=json,
            timeout=self.config.timeout_seconds,
        )
        self._raise_for_response(response)
        payload = response.json()
        self._raise_for_kis_error(payload)
        return payload

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
