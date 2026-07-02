from __future__ import annotations

import time
from typing import Any

import requests

from datahub.models import PriceBar


class KISPriceDownloader:
    """KIS REST market-data adapter for normalized ADE PriceBar records.

    v1 target:
    - Korean domestic stock quote
    - Korean domestic daily OHLCV
    - conversion into datahub.models.PriceBar
    """

    PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
    LIVE_BASE_URL = "https://openapi.koreainvestment.com:9443"

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        environment: str = "paper",
        base_url: str | None = None,
        session: requests.Session | None = None,
        timeout_seconds: int = 10,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.environment = environment
        self.base_url = base_url or (self.LIVE_BASE_URL if environment == "live" else self.PAPER_BASE_URL)
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0

    def get_quote(self, ticker: str) -> dict[str, Any]:
        """Return raw KIS domestic-stock current-price payload."""
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker}
        return self._get("/uapi/domestic-stock/v1/quotations/inquire-price", "FHKST01010100", params)

    def download_daily_bars(
        self,
        ticker: str,
        start: str,
        end: str,
        market: str = "kr",
        period_code: str = "D",
    ) -> list[PriceBar]:
        """Download daily bars and normalize into ADE PriceBar records.

        Dates must be passed as YYYYMMDD strings because KIS domestic chart APIs use compact dates.
        """
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": start,
            "FID_INPUT_DATE_2": end,
            "FID_PERIOD_DIV_CODE": period_code,
            "FID_ORG_ADJ_PRC": "0",
        }
        payload = self._get("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100", params)
        rows = payload.get("output2") or []
        records: list[PriceBar] = []
        for row in rows:
            trade_date = self._format_date(str(row.get("stck_bsop_date", "")))
            if not trade_date:
                continue
            records.append(
                PriceBar(
                    market=market,
                    ticker=ticker,
                    trade_date=trade_date,
                    open=self._to_float(row.get("stck_oprc")),
                    high=self._to_float(row.get("stck_hgpr")),
                    low=self._to_float(row.get("stck_lwpr")),
                    close=self._to_float(row.get("stck_clpr")),
                    volume=self._to_float(row.get("acml_vol")),
                    adjusted_close=None,
                    source="kis",
                )
            )
        return sorted(records, key=lambda item: item.trade_date)

    def _headers(self, tr_id: str) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self._token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "content-type": "application/json; charset=utf-8",
        }

    def _token(self) -> str:
        if self._access_token and time.time() < self._access_token_expires_at - 60:
            return self._access_token
        response = self.session.post(
            f"{self.base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError(f"KIS token response did not include access_token: {payload}")
        self._access_token = str(token)
        self._access_token_expires_at = time.time() + int(payload.get("expires_in", 24 * 60 * 60))
        return self._access_token

    def _get(self, path: str, tr_id: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}{path}",
            headers=self._headers(tr_id),
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("rt_cd") not in {None, "0"}:
            raise RuntimeError(f"KIS API error: {payload.get('msg_cd')} {payload.get('msg1')}")
        return payload

    @staticmethod
    def _format_date(value: str) -> str | None:
        if len(value) != 8 or not value.isdigit():
            return None
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0
