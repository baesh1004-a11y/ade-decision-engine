from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class StrategySignal:
    strategy_name: str
    score: float
    signal: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategyLibraryEngine:
    """Evaluate multiple strategy archetypes on the same market data."""

    def evaluate(self, df: pd.DataFrame) -> dict[str, Any]:
        signals = [
            self._breakout(df),
            self._pullback(df),
            self._trend_following(df),
            self._momentum(df),
            self._mean_reversion(df),
            self._swing(df),
        ]
        best = max(signals, key=lambda item: item.score)
        return {
            "engine_version": "strategy-library-v1.0.0",
            "best_strategy": best.to_dict(),
            "signals": [item.to_dict() for item in signals],
            "strategy_scores": {item.strategy_name: round(item.score, 4) for item in signals},
        }

    def _breakout(self, df: pd.DataFrame) -> StrategySignal:
        close = float(df["Close"].iloc[-1])
        high20 = float(df["High"].tail(20).max())
        score = 100.0 if close >= high20 * 0.995 else 60.0 if close >= high20 * 0.97 else 30.0
        return StrategySignal("breakout", score, "BUY" if score >= 70 else "WATCH", "20-day high breakout proximity")

    def _pullback(self, df: pd.DataFrame) -> StrategySignal:
        row = df.iloc[-1]
        close = float(row.get("Close", 0.0))
        ma20 = float(row.get("MA20", close)) if not pd.isna(row.get("MA20", close)) else close
        ma60 = float(row.get("MA60", ma20)) if not pd.isna(row.get("MA60", ma20)) else ma20
        score = 85.0 if ma60 < close <= ma20 * 1.03 else 45.0
        return StrategySignal("pullback", score, "BUY" if score >= 70 else "WATCH", "Pullback near moving average support")

    def _trend_following(self, df: pd.DataFrame) -> StrategySignal:
        row = df.iloc[-1]
        close = float(row.get("Close", 0.0))
        ma20 = float(row.get("MA20", close)) if not pd.isna(row.get("MA20", close)) else close
        ma60 = float(row.get("MA60", ma20)) if not pd.isna(row.get("MA60", ma20)) else ma20
        score = 90.0 if close > ma20 > ma60 else 50.0
        return StrategySignal("trend_following", score, "BUY" if score >= 70 else "WATCH", "Trend alignment")

    def _momentum(self, df: pd.DataFrame) -> StrategySignal:
        if len(df) < 21:
            return StrategySignal("momentum", 40.0, "WATCH", "Insufficient lookback")
        ret20 = float(df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1.0)
        score = 90.0 if ret20 > 0.1 else 70.0 if ret20 > 0.04 else 35.0
        return StrategySignal("momentum", score, "BUY" if score >= 70 else "WATCH", "20-day momentum")

    def _mean_reversion(self, df: pd.DataFrame) -> StrategySignal:
        close = df["Close"].astype(float)
        z = 0.0
        if len(close) >= 20 and close.tail(20).std() > 0:
            z = float((close.iloc[-1] - close.tail(20).mean()) / close.tail(20).std())
        score = 80.0 if z < -1.5 else 50.0 if z < -0.5 else 25.0
        return StrategySignal("mean_reversion", score, "BUY" if score >= 70 else "WATCH", "Mean reversion z-score")

    def _swing(self, df: pd.DataFrame) -> StrategySignal:
        low5 = float(df["Low"].tail(5).min())
        close = float(df["Close"].iloc[-1])
        score = 75.0 if close > low5 * 1.03 else 45.0
        return StrategySignal("swing", score, "BUY" if score >= 70 else "WATCH", "Short-term swing recovery")
