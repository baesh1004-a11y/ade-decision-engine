import pandas as pd
import yfinance as yf


class USACollector:
    """Collect OHLCV data from Yahoo Finance using yfinance."""

    def get_daily(self, ticker: str, period: str = "10y", interval: str = "1d") -> pd.DataFrame:
        df = yf.download(ticker, period=period, interval=interval, auto_adjust=False, progress=False)
        if df.empty:
            raise ValueError(f"No data returned for ticker: {ticker}")
        df = df.reset_index()
        df = df.rename(columns={
            "Date": "Date",
            "Open": "Open",
            "High": "High",
            "Low": "Low",
            "Close": "Close",
            "Volume": "Volume",
        })
        return df[["Date", "Open", "High", "Low", "Close", "Volume"]]
