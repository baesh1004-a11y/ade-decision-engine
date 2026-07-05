from __future__ import annotations

import math
from typing import Iterable

import pandas as pd

from recommendation.models import RecommendationInput, RecommendationReport, RecommendationScore


class RecommendationEngine:
    """ADE Recommendation Engine v1.

    Scores a multi-market stock universe and returns explainable Top-N picks.
    The engine is deterministic and data-driven so it can be backtested later.
    """

    REQUIRED_COLUMNS = {"Close", "Volume"}

    def rank(self, universe: Iterable[RecommendationInput], top_n: int = 10) -> RecommendationReport:
        items = list(universe)
        scored = [self.score(item) for item in items]
        scored = sorted(scored, key=lambda item: (item.final_score, item.confidence), reverse=True)
        selected = scored[:top_n]
        return RecommendationReport(
            title="ADE Daily Picks",
            total_universe=len(items),
            selected_count=len(selected),
            recommendations=selected,
        )

    def score(self, item: RecommendationInput) -> RecommendationScore:
        df = self._normalize(item.market_data)
        self._validate(df)

        close = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else close
        volume = float(df["Volume"].iloc[-1])

        ma20 = float(df["Close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else close
        ma60 = float(df["Close"].rolling(60).mean().iloc[-1]) if len(df) >= 60 else ma20
        ma120 = float(df["Close"].rolling(120).mean().iloc[-1]) if len(df) >= 120 else ma60
        vol20 = float(df["Volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else max(volume, 1.0)
        rsi = self._rsi(df["Close"], period=14)
        volatility = self._volatility(df["Close"])
        return_20 = self._return(df["Close"], 20)
        return_60 = self._return(df["Close"], 60)
        volume_ratio = volume / vol20 if vol20 > 0 else 1.0

        trend_score, trend_reasons = self._trend_score(close, ma20, ma60, ma120, return_60)
        volume_score, volume_reasons = self._volume_score(volume_ratio)
        momentum_score, momentum_reasons = self._momentum_score(rsi, return_20)
        volatility_score, volatility_reasons = self._volatility_score(volatility)
        pattern_score, pattern_reasons = self._pattern_score(close, prev_close, ma20, volume_ratio)
        risk_score, risk_flags = self._risk_score(close, ma120, volatility, rsi)
        confidence_score = self._confidence_score(len(df), trend_score, volume_score, momentum_score, risk_score)

        components = {
            "trend": trend_score,
            "volume": volume_score,
            "momentum": momentum_score,
            "volatility": volatility_score,
            "pattern": pattern_score,
            "risk": risk_score,
            "confidence": confidence_score,
        }
        final_score = max(0, min(100, sum(components.values())))
        confidence = round(confidence_score / 10, 2)
        grade = self._grade(final_score)
        action = self._action(final_score, confidence, risk_flags)
        reasons = trend_reasons + volume_reasons + momentum_reasons + volatility_reasons + pattern_reasons

        return RecommendationScore(
            market=item.market,
            ticker=item.ticker,
            name=item.name,
            sector=item.sector,
            final_score=final_score,
            grade=grade,
            action=action,
            confidence=confidence,
            components=components,
            reasons=reasons[:8],
            risk_flags=risk_flags,
        )

    def _normalize(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        aliases = {
            "close": "Close",
            "volume": "Volume",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "date": "Date",
        }
        for src, dst in aliases.items():
            if src in df.columns and dst not in df.columns:
                df[dst] = df[src]
        return df.dropna(subset=["Close", "Volume"]).reset_index(drop=True)

    def _validate(self, df: pd.DataFrame) -> None:
        missing = self.REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"Recommendation requires columns: {', '.join(sorted(missing))}")
        if len(df) < 30:
            raise ValueError("Recommendation requires at least 30 rows of market data")

    def _trend_score(self, close: float, ma20: float, ma60: float, ma120: float, return_60: float) -> tuple[int, list[str]]:
        score = 0
        reasons = []
        if close > ma20:
            score += 5
            reasons.append("Price is above MA20")
        if ma20 > ma60:
            score += 5
            reasons.append("MA20 is above MA60")
        if ma60 >= ma120:
            score += 5
            reasons.append("Medium-term trend is stable")
        if return_60 > 0.05:
            score += 5
            reasons.append("60-day return is positive")
        return min(score, 20), reasons

    def _volume_score(self, volume_ratio: float) -> tuple[int, list[str]]:
        if volume_ratio >= 2.0:
            return 15, ["Volume is more than 2x the 20-day average"]
        if volume_ratio >= 1.5:
            return 12, ["Volume is expanding strongly"]
        if volume_ratio >= 1.1:
            return 8, ["Volume is above average"]
        if volume_ratio >= 0.8:
            return 4, ["Volume is normal"]
        return 1, ["Volume is weak"]

    def _momentum_score(self, rsi: float, return_20: float) -> tuple[int, list[str]]:
        score = 0
        reasons = []
        if 45 <= rsi <= 68:
            score += 10
            reasons.append("RSI is in a healthy momentum range")
        elif 35 <= rsi < 45:
            score += 7
            reasons.append("RSI is recovering from a low zone")
        elif 68 < rsi <= 75:
            score += 5
            reasons.append("RSI is strong but approaching overheated")
        else:
            score += 2
            reasons.append("RSI is outside the preferred range")

        if return_20 > 0.03:
            score += 10
            reasons.append("20-day momentum is positive")
        elif return_20 > 0:
            score += 6
            reasons.append("20-day momentum is mildly positive")
        else:
            score += 2
            reasons.append("20-day momentum is weak")
        return min(score, 20), reasons

    def _volatility_score(self, volatility: float) -> tuple[int, list[str]]:
        if volatility <= 0.015:
            return 10, ["Volatility is controlled"]
        if volatility <= 0.025:
            return 8, ["Volatility is acceptable"]
        if volatility <= 0.04:
            return 5, ["Volatility is elevated"]
        return 2, ["Volatility is high"]

    def _pattern_score(self, close: float, prev_close: float, ma20: float, volume_ratio: float) -> tuple[int, list[str]]:
        score = 0
        reasons = []
        if close > prev_close:
            score += 4
            reasons.append("Latest candle closed higher than previous close")
        if close > ma20:
            score += 5
            reasons.append("Price reclaimed short-term trend")
        if volume_ratio >= 1.2:
            score += 6
            reasons.append("Price action is supported by volume")
        return min(score, 15), reasons

    def _risk_score(self, close: float, ma120: float, volatility: float, rsi: float) -> tuple[int, list[str]]:
        score = 10
        flags = []
        if ma120 > 0 and close < ma120:
            score -= 4
            flags.append("Below MA120")
        if volatility > 0.04:
            score -= 3
            flags.append("High volatility")
        if rsi >= 80:
            score -= 3
            flags.append("RSI overheated")
        return max(0, score), flags

    def _confidence_score(self, rows: int, trend: int, volume: int, momentum: int, risk: int) -> int:
        score = 0
        if rows >= 120:
            score += 3
        elif rows >= 60:
            score += 2
        else:
            score += 1
        if trend >= 15:
            score += 2
        if volume >= 8:
            score += 2
        if momentum >= 14:
            score += 2
        if risk >= 7:
            score += 1
        return min(score, 10)

    def _rsi(self, close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, math.nan)
        rsi = 100 - (100 / (1 + rs))
        value = rsi.iloc[-1]
        if pd.isna(value):
            return 50.0
        return float(value)

    def _volatility(self, close: pd.Series) -> float:
        returns = close.pct_change().dropna()
        if returns.empty:
            return 0.0
        window = returns.tail(20)
        return float(window.std())

    def _return(self, close: pd.Series, days: int) -> float:
        if len(close) <= days:
            return 0.0
        base = float(close.iloc[-days - 1])
        if base <= 0:
            return 0.0
        return float(close.iloc[-1] / base - 1)

    def _grade(self, score: int) -> str:
        if score >= 90:
            return "A+"
        if score >= 80:
            return "A"
        if score >= 70:
            return "B"
        if score >= 60:
            return "C"
        return "D"

    def _action(self, score: int, confidence: float, risk_flags: list[str]) -> str:
        if score >= 85 and confidence >= 0.7 and not risk_flags:
            return "STRONG_BUY_CANDIDATE"
        if score >= 75 and confidence >= 0.6:
            return "BUY_CANDIDATE"
        if score >= 65:
            return "WATCHLIST"
        return "REJECT"
