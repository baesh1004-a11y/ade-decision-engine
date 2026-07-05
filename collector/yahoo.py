from __future__ import annotations

import pandas as pd

from collector.base import CollectorRequest, CollectorResult, standardize_ohlcv


class YahooCollector:
    """Yahoo Finance OHLCV collector for US stocks and ETFs.

    This is the first real-data collector for ADE. It intentionally returns
    standardized DataFrames so DataHub/Recommendation do not depend on Yahoo.
    """

    source = "yahoo"

    def fetch(self, request: CollectorRequest) -> CollectorResult:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("yfinance is required. Install it with: pip install yfinance") from exc

        raw = yf.download(
            request.ticker,
            period=request.period,
            interval=request.interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        data = standardize_ohlcv(raw)
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

    def _quality_score(self, data: pd.DataFrame) -> int:
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
