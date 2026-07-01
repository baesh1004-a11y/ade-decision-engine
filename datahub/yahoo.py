from __future__ import annotations

import pandas as pd

from datahub.loaders import CSVPriceLoader
from datahub.models import PriceBar


class YahooPriceDownloader:
    """Yahoo Finance downloader using optional yfinance dependency."""

    def download(self, ticker: str, market: str = "us", start: str | None = None, end: str | None = None) -> list[PriceBar]:
        try:
            import yfinance as yf
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("Yahoo downloader requires yfinance. Install with: pip install yfinance") from exc

        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
        if df.empty:
            return []
        df = df.reset_index()
        if "Date" not in df.columns:
            df = df.rename(columns={df.columns[0]: "Date"})
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        return CSVPriceLoader().from_dataframe(df, market=market, ticker=ticker, source="yahoo")
