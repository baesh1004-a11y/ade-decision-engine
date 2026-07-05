from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from collector.base import CollectorRequest, CollectorResult, standardize_ohlcv


_PERIOD_DAYS = {
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 366,
    "2y": 731,
    "5y": 1826,
}


class FDRCollector:
    """FinanceDataReader-based OHLCV collector for Korean and US markets."""

    source = "fdr"

    def fetch(self, request: CollectorRequest) -> CollectorResult:
        if request.interval != "1d":
            return self._failure(request, "FDRCollector currently supports interval='1d' only")

        try:
            import FinanceDataReader as fdr
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "FinanceDataReader is required. Install it with: pip install finance-datareader"
            ) from exc

        start, end = self._date_range(request.period)

        try:
            raw = fdr.DataReader(request.ticker, start=start, end=end)
            data = standardize_ohlcv(raw)
        except Exception as exc:
            return self._failure(request, f"collection failed: {exc}")

        quality = self._quality_score(data)
        message = "ok" if not data.empty else "empty data"
        return CollectorResult(
            market=request.market,
            ticker=request.ticker,
            source=self.source,
            data=data,
            quality_score=quality,
            message=message,
        )

    @staticmethod
    def _date_range(period: str) -> tuple[str | None, str | None]:
        if period == "max":
            return None, None

        days = _PERIOD_DAYS.get(period)
        if days is None:
            raise ValueError(
                "Unsupported period. Use one of: 1mo, 3mo, 6mo, 1y, 2y, 5y, max"
            )

        end = date.today()
        start = end - timedelta(days=days)
        return start.isoformat(), end.isoformat()

    def _failure(self, request: CollectorRequest, message: str) -> CollectorResult:
        empty = pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        return CollectorResult(
            market=request.market,
            ticker=request.ticker,
            source=self.source,
            data=empty,
            quality_score=0,
            message=message,
        )

    @staticmethod
    def _quality_score(data: pd.DataFrame) -> int:
        if data.empty:
            return 0

        score = 100
        if len(data) < 60:
            score -= 20

        missing_ratio = data[["Open", "High", "Low", "Close", "Volume"]].isna().mean().mean()
        score -= int(missing_ratio * 50)

        if (data["Close"] <= 0).any():
            score -= 30

        return max(0, min(100, score))
