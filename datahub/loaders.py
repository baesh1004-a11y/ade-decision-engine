from __future__ import annotations

from pathlib import Path

import pandas as pd

from datahub.models import PriceBar


class CSVPriceLoader:
    """Load OHLCV CSV files into normalized PriceBar records."""

    REQUIRED_COLUMNS = {"Date", "Open", "High", "Low", "Close", "Volume"}

    def load(self, path: str | Path, market: str, ticker: str, source: str = "csv") -> list[PriceBar]:
        df = pd.read_csv(path)
        return self.from_dataframe(df, market=market, ticker=ticker, source=source)

    def from_dataframe(self, df: pd.DataFrame, market: str, ticker: str, source: str = "dataframe") -> list[PriceBar]:
        missing = self.REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"CSV price data requires columns: {', '.join(sorted(missing))}")
        records: list[PriceBar] = []
        for _, row in df.iterrows():
            records.append(
                PriceBar(
                    market=market,
                    ticker=ticker,
                    trade_date=str(row["Date"]),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                    adjusted_close=float(row["Adj Close"]) if "Adj Close" in df.columns and not pd.isna(row["Adj Close"]) else None,
                    source=source,
                )
            )
        return records
