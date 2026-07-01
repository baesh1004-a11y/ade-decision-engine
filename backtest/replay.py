from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import pandas as pd


@dataclass(frozen=True)
class ReplayFrame:
    step: int
    trade_date: str
    history: pd.DataFrame


class ReplayEngine:
    """Replay historical OHLCV data one date at a time without future leakage."""

    def __init__(self, min_history: int = 80) -> None:
        if min_history < 1:
            raise ValueError("min_history must be greater than zero")
        self.min_history = min_history

    def replay(self, df: pd.DataFrame) -> Iterator[ReplayFrame]:
        self._validate(df)
        for end_index in range(self.min_history - 1, len(df)):
            history = df.iloc[: end_index + 1].copy()
            yield ReplayFrame(
                step=end_index,
                trade_date=self._trade_date(df, end_index),
                history=history,
            )

    def _validate(self, df: pd.DataFrame) -> None:
        required = {"Open", "High", "Low", "Close", "Volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Replay requires columns: {', '.join(sorted(missing))}")
        if len(df) < self.min_history:
            raise ValueError(f"Replay requires at least {self.min_history} rows")

    def _trade_date(self, df: pd.DataFrame, end_index: int) -> str:
        if "Date" in df.columns:
            return str(df.iloc[end_index]["Date"])
        idx = df.index[end_index]
        return str(idx.date()) if hasattr(idx, "date") else str(end_index)
