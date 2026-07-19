from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from broker.kis import KISBrokerAdapter, kis_config_from_env
from markets.symbol_display import normalize_ticker


class KISMarketDataClient(KISBrokerAdapter):
    """KIS domestic-equity quote and chart reader.

    Market-data access is intentionally independent from the live-order gate.
    Orders remain protected by KIS_LIVE_ORDER_ENABLED in KISTradingAdapter.
    """

    def get_current_quote(self, ticker: str) -> dict[str, object]:
        code = normalize_ticker(ticker, "kr")
        payload = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
            },
        )
        row = payload.get("output") or {}
        if not isinstance(row, dict):
            row = {}
        return {
            "ticker": code,
            "current_price": self._to_float(row.get("stck_prpr")),
            "change": self._to_float(row.get("prdy_vrss")),
            "change_rate": self._to_float(row.get("prdy_ctrt")),
            "open": self._to_float(row.get("stck_oprc")),
            "high": self._to_float(row.get("stck_hgpr")),
            "low": self._to_float(row.get("stck_lwpr")),
            "volume": self._to_float(row.get("acml_vol")),
            "trade_amount": self._to_float(row.get("acml_tr_pbmn")),
            "ask_price": self._to_float(row.get("askp")),
            "bid_price": self._to_float(row.get("bidp")),
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "raw": row,
        }

    @staticmethod
    def _clean_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame
        frame = frame.dropna(subset=["Date", "Open", "High", "Low", "Close"])
        frame = frame[(frame[["Open", "High", "Low", "Close"]] > 0).all(axis=1)]
        frame["Volume"] = pd.to_numeric(frame["Volume"], errors="coerce").fillna(0.0)
        return frame.sort_values("Date").drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)

    def get_daily_bars(self, ticker: str, *, lookback_days: int = 240) -> pd.DataFrame:
        """Return KIS daily OHLCV bars for technical-analysis charts."""
        code = normalize_ticker(ticker, "kr")
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=max(lookback_days, 60))
        payload = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            tr_id="FHKST03010100",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",
            },
        )
        rows = payload.get("output2") or []
        if not isinstance(rows, list):
            return pd.DataFrame()

        normalized: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            date_text = str(row.get("stck_bsop_date") or "")
            if len(date_text) != 8:
                continue
            normalized.append(
                {
                    "Date": pd.to_datetime(date_text, format="%Y%m%d", errors="coerce"),
                    "Open": self._to_float(row.get("stck_oprc")),
                    "High": self._to_float(row.get("stck_hgpr")),
                    "Low": self._to_float(row.get("stck_lwpr")),
                    "Close": self._to_float(row.get("stck_clpr")),
                    "Volume": self._to_float(row.get("acml_vol")),
                }
            )
        return self._clean_frame(normalized)

    def get_intraday_bars(self, ticker: str, *, include_previous: bool = True) -> pd.DataFrame:
        code = normalize_ticker(ticker, "kr")
        payload = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            tr_id="FHKST03010200",
            params={
                "FID_ETC_CLS_CODE": "",
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_HOUR_1": datetime.now().strftime("%H%M%S"),
                "FID_PW_DATA_INCU_YN": "Y" if include_previous else "N",
            },
        )
        rows = payload.get("output2") or []
        if not isinstance(rows, list):
            return pd.DataFrame()

        normalized: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            date_text = str(row.get("stck_bsop_date") or "")
            time_text = str(row.get("stck_cntg_hour") or "")
            if len(date_text) != 8 or len(time_text) != 6:
                continue
            normalized.append(
                {
                    "Date": pd.to_datetime(date_text + time_text, format="%Y%m%d%H%M%S", errors="coerce"),
                    "Open": self._to_float(row.get("stck_oprc")),
                    "High": self._to_float(row.get("stck_hgpr")),
                    "Low": self._to_float(row.get("stck_lwpr")),
                    "Close": self._to_float(row.get("stck_prpr")),
                    "Volume": self._to_float(row.get("cntg_vol")),
                }
            )
        return self._clean_frame(normalized)

    def get_four_hour_bars(self, ticker: str) -> pd.DataFrame:
        """Aggregate available KIS intraday bars into four-hour OHLCV bars."""
        frame = self.get_intraday_bars(ticker, include_previous=True)
        if frame.empty:
            return frame
        indexed = frame.set_index("Date")
        aggregated = indexed.resample("4h", origin="start_day", offset="9h").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        )
        return self._clean_frame(aggregated.dropna(subset=["Open", "Close"]).reset_index())


def kis_market_data_from_env() -> KISMarketDataClient:
    return KISMarketDataClient(kis_config_from_env())