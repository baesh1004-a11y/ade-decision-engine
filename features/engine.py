from __future__ import annotations

import pandas as pd


class FeatureEngine:
    """Compute deterministic technical features from ADE-standard OHLCV data."""

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        if data.empty:
            return data.copy()

        df = data.copy().sort_values("Date").reset_index(drop=True)
        close = pd.to_numeric(df["Close"], errors="coerce")
        high = pd.to_numeric(df["High"], errors="coerce")
        low = pd.to_numeric(df["Low"], errors="coerce")
        volume = pd.to_numeric(df["Volume"], errors="coerce")

        for window in (5, 20, 60, 120):
            df[f"MA{window}"] = close.rolling(window).mean()

        df["EMA12"] = close.ewm(span=12, adjust=False).mean()
        df["EMA26"] = close.ewm(span=26, adjust=False).mean()
        df["MACD"] = df["EMA12"] - df["EMA26"]
        df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, pd.NA)
        df["RSI14"] = (100 - (100 / (1 + rs))).fillna(50.0)

        prev_close = close.shift(1)
        true_range = pd.concat(
            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
        ).max(axis=1)
        df["ATR14"] = true_range.rolling(14).mean()

        std20 = close.rolling(20).std()
        df["BB_MID"] = df["MA20"]
        df["BB_UPPER"] = df["MA20"] + (2 * std20)
        df["BB_LOWER"] = df["MA20"] - (2 * std20)
        df["VOLUME_MA20"] = volume.rolling(20).mean()
        df["VOLUME_RATIO"] = volume / df["VOLUME_MA20"].replace(0, pd.NA)
        df["RETURN_1D"] = close.pct_change()
        df["RETURN_20D"] = close.pct_change(20)
        df["VOLATILITY_20D"] = df["RETURN_1D"].rolling(20).std()
        df["HIGH_52W"] = high.rolling(252, min_periods=20).max()
        df["LOW_52W"] = low.rolling(252, min_periods=20).min()
        return df
