from __future__ import annotations

import pandas as pd


class ReplayEventAnalyzer:
    """Analyze flow after a money event.

    ADE compares the chart after a money explosion. A later money event is part of
    the replay flow, so it should not cut the flow short. The first stable rule is:
    - follow the event for max_flow_days,
    - stop early only when a deep drawdown invalidates the pattern.
    """

    def __init__(self, max_flow_days: int = 240, drawdown_limit_pct: float = -35.0) -> None:
        self.max_flow_days = max_flow_days
        self.drawdown_limit_pct = drawdown_limit_pct

    def end_index(self, df: pd.DataFrame, event_index: int) -> tuple[int, str]:
        close = df["Close"]
        entry = float(close.iloc[event_index])
        last_index = min(len(df) - 1, event_index + self.max_flow_days)
        for i in range(event_index + 1, last_index + 1):
            low_return = (float(df.iloc[i]["Low"]) / entry - 1) * 100 if entry > 0 else 0
            if low_return <= self.drawdown_limit_pct:
                return i, "DEEP_DRAWDOWN"
        return last_index, "MAX_FLOW_WINDOW"

    @staticmethod
    def max_return(df: pd.DataFrame, event_index: int, end_index: int) -> float | None:
        entry = float(df.iloc[event_index]["Close"])
        if entry <= 0:
            return None
        highs = df.iloc[event_index + 1 : end_index + 1]["High"]
        if highs.empty:
            return None
        return round((float(highs.max()) / entry - 1) * 100, 2)

    @staticmethod
    def max_drawdown(df: pd.DataFrame, event_index: int, end_index: int) -> float | None:
        entry = float(df.iloc[event_index]["Close"])
        if entry <= 0:
            return None
        lows = df.iloc[event_index + 1 : end_index + 1]["Low"]
        if lows.empty:
            return None
        return round((float(lows.min()) / entry - 1) * 100, 2)
