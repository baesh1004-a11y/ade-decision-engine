import pandas as pd
import yfinance as yf


class USACollector:
    """Collect OHLCV data from Yahoo Finance using yfinance."""

    def get_daily(self, ticker: str, period: str = "10y", interval: str = "1d") -> pd.DataFrame:
        df = yf.download(ticker, period=period, interval=interval, auto_adjust=False, progress=False)
        if df.empty:
            raise ValueError(f"No data returned for ticker: {ticker}")

        # yfinance can return MultiIndex columns for some requests.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        df = df.reset_index()
        if "Datetime" in df.columns and "Date" not in df.columns:
            df = df.rename(columns={"Datetime": "Date"})

        required = ["Date", "Open", "High", "Low", "Close", "Volume"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing expected yfinance columns: {missing}")

        return df[required].dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)
