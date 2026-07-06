from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class WeeklyPattern:
    pattern: str
    vector: list[float]
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class WeeklyPatternEngine:
    FEATURE_NAMES = ["weekly_position", "weekly_trend", "weekly_box", "weekly_breakout", "weekly_pullback"]

    def extract(self, data: pd.DataFrame) -> WeeklyPattern:
        weekly = self._to_weekly(data)
        if len(weekly) < 8:
            return WeeklyPattern("WEEKLY_UNKNOWN", [0.5, 0, 0, 0, 0], ["weekly_unknown"])
        close = weekly["Close"]
        high = weekly["High"]
        low = weekly["Low"]
        latest = float(close.iloc[-1])
        high_52 = float(high.tail(52).max())
        low_52 = float(low.tail(52).min())
        position = 0.5 if high_52 == low_52 else self._clip((latest - low_52) / (high_52 - low_52), 0, 1)
        ma4 = close.rolling(4, min_periods=2).mean()
        ma13 = close.rolling(13, min_periods=4).mean()
        ma26 = close.rolling(26, min_periods=8).mean()
        trend = 1.0 if latest > ma4.iloc[-1] > ma13.iloc[-1] > ma26.iloc[-1] else 0.7 if latest > ma13.iloc[-1] > ma26.iloc[-1] else 0.35 if latest > ma13.iloc[-1] else 0.0
        prior = weekly.tail(30).iloc[:-1]
        box = 0.0
        breakout = 0.0
        if not prior.empty:
            prior_high = float(prior["High"].max())
            prior_low = float(prior["Low"].min())
            width = (prior_high - prior_low) / prior_low if prior_low else 9.9
            box = 1.0 if width <= 0.35 else 0.7 if width <= 0.55 else 0.35 if width <= 0.85 else 0.0
            breakout = 1.0 if latest >= prior_high else 0.7 if latest >= prior_high * 0.95 else 0.0
        recent_high = float(high.tail(8).max())
        pullback = self._clip((recent_high - latest) / recent_high if recent_high else 0, 0, 0.35) / 0.35
        vector = [round(position, 6), round(trend, 6), round(box, 6), round(breakout, 6), round(pullback, 6)]
        if breakout >= 0.7:
            return WeeklyPattern("WEEKLY_BREAKOUT", vector, ["weekly_breakout"])
        if trend >= 0.7 and pullback > 0.15:
            return WeeklyPattern("WEEKLY_UPTREND_PULLBACK", vector, ["weekly_uptrend_pullback"])
        if box >= 0.7:
            return WeeklyPattern("WEEKLY_BOX", vector, ["weekly_box"])
        if position >= 0.75:
            return WeeklyPattern("WEEKLY_UPPER", vector, ["weekly_upper"])
        return WeeklyPattern("WEEKLY_MIXED", vector, ["weekly_mixed"])

    @staticmethod
    def similarity(a: WeeklyPattern, b: WeeklyPattern) -> float:
        distance = sum((x - y) ** 2 for x, y in zip(a.vector, b.vector)) ** 0.5
        return round(max(0.0, 100.0 / (1.0 + distance)), 2)

    @staticmethod
    def _to_weekly(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" not in df.columns:
            df = df.reset_index().rename(columns={"index": "Date"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).sort_values("Date")
        return df.set_index("Date").resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna().reset_index()

    @staticmethod
    def _clip(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))
