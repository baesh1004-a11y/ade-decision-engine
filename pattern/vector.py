from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


VECTOR_VERSION = "pattern-vector-v1.0.0"


DEFAULT_VECTOR_COLUMNS = [
    "Close",
    "Volume",
    "MA5",
    "MA20",
    "MA60",
    "MA120",
    "MA240",
    "VOL20_RATIO",
    "BODY_RATIO",
    "STO533_K",
    "STO533_D",
    "STO1066_K",
    "STO1066_D",
    "STO201212_K",
    "STO201212_D",
]


@dataclass(frozen=True)
class PatternVector:
    ticker: str
    end_index: int
    window: int
    vector_version: str
    values: list[float]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PatternVectorizer:
    """Convert OHLCV windows into normalized numerical pattern vectors.

    v1.0 intentionally avoids external vector databases. The output vector is
    deterministic and can be compared with cosine similarity.
    """

    def __init__(self, window: int = 20) -> None:
        if window < 5:
            raise ValueError("window must be at least 5")
        self.window = window

    def transform_window(self, df: pd.DataFrame, end_index: int, ticker: str = "UNKNOWN") -> PatternVector:
        self._validate(df)
        if end_index < self.window - 1:
            raise ValueError("end_index does not have enough lookback window")
        if end_index >= len(df):
            raise ValueError("end_index is out of range")

        window_df = df.iloc[end_index - self.window + 1 : end_index + 1].copy()
        values = self._build_vector(window_df)
        last = window_df.iloc[-1]
        return PatternVector(
            ticker=ticker,
            end_index=end_index,
            window=self.window,
            vector_version=VECTOR_VERSION,
            values=values,
            metadata={
                "close": float(last["Close"]),
                "volume": float(last.get("Volume", 0.0)),
            },
        )

    def transform_latest(self, df: pd.DataFrame, ticker: str = "UNKNOWN") -> PatternVector:
        return self.transform_window(df, end_index=len(df) - 1, ticker=ticker)

    def transform_history(self, df: pd.DataFrame, ticker: str = "UNKNOWN") -> list[PatternVector]:
        self._validate(df)
        if len(df) < self.window:
            return []
        return [self.transform_window(df, end_index=i, ticker=ticker) for i in range(self.window - 1, len(df))]

    def _validate(self, df: pd.DataFrame) -> None:
        required = {"Open", "High", "Low", "Close", "Volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Pattern vectorization requires columns: {', '.join(sorted(missing))}")
        if df.empty:
            raise ValueError("Cannot vectorize an empty dataframe")

    def _build_vector(self, window_df: pd.DataFrame) -> list[float]:
        close = window_df["Close"].astype(float).to_numpy()
        open_ = window_df["Open"].astype(float).to_numpy()
        high = window_df["High"].astype(float).to_numpy()
        low = window_df["Low"].astype(float).to_numpy()
        volume = window_df["Volume"].astype(float).to_numpy()

        base = close[0]
        if base <= 0:
            raise ValueError("first close in pattern window must be greater than zero")

        close_norm = (close / base) - 1.0
        body = (close - open_) / np.maximum(close, 1e-9)
        candle_range = (high - low) / np.maximum(close, 1e-9)
        upper_wick = (high - np.maximum(open_, close)) / np.maximum(close, 1e-9)
        lower_wick = (np.minimum(open_, close) - low) / np.maximum(close, 1e-9)
        volume_norm = self._zscore(np.log1p(volume))

        vector = np.concatenate(
            [
                self._zscore(close_norm),
                self._zscore(body),
                self._zscore(candle_range),
                self._zscore(upper_wick),
                self._zscore(lower_wick),
                volume_norm,
            ]
        )
        return [round(float(x), 6) for x in vector]

    def _zscore(self, arr: np.ndarray) -> np.ndarray:
        std = float(np.nanstd(arr))
        if std == 0 or np.isnan(std):
            return np.zeros_like(arr, dtype=float)
        return (arr - float(np.nanmean(arr))) / std


def vectorize_latest(df: pd.DataFrame, ticker: str = "UNKNOWN", window: int = 20) -> dict[str, Any]:
    return PatternVectorizer(window=window).transform_latest(df, ticker=ticker).to_dict()


# Backward-compatible helpers kept for older tests/callers.
def build_latest_vector(df: pd.DataFrame, columns: list[str] | None = None) -> pd.Series:
    cols = columns or DEFAULT_VECTOR_COLUMNS
    available = [col for col in cols if col in df.columns]
    if not available:
        raise ValueError("No vector columns are available in dataframe.")
    latest = df[available].iloc[-1].astype(float)
    return latest.fillna(0.0)


def build_window_vector(df: pd.DataFrame, window: int = 60, columns: list[str] | None = None) -> pd.Series:
    cols = columns or DEFAULT_VECTOR_COLUMNS
    available = [col for col in cols if col in df.columns]
    if len(df) < window:
        raise ValueError(f"Not enough rows. Need {window}, got {len(df)}")
    window_df = df[available].tail(window).astype(float).fillna(0.0)
    return pd.Series(window_df.to_numpy().flatten())
