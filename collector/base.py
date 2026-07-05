from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class CollectorRequest:
    market: str
    ticker: str
    period: str = "6mo"
    interval: str = "1d"


@dataclass(frozen=True)
class CollectorResult:
    market: str
    ticker: str
    source: str
    data: pd.DataFrame
    quality_score: int
    message: str = ""


class MarketDataCollector(Protocol):
    source: str

    def fetch(self, request: CollectorRequest) -> CollectorResult:
        ...


def standardize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Return ADE-standard OHLCV columns: Date, Open, High, Low, Close, Volume."""

    if df.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

    data = df.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

    if "Date" not in data.columns:
        data = data.reset_index()

    aliases = {
        "index": "Date",
        "Datetime": "Date",
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adj close": "Close",
        "Adj Close": "Close",
        "volume": "Volume",
    }
    for src, dst in aliases.items():
        if src in data.columns and dst not in data.columns:
            data[dst] = data[src]

    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns: {', '.join(missing)}")

    data = data[required].dropna(subset=["Close", "Volume"]).reset_index(drop=True)
    return data
