from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class STOLayers:
    short: float
    middle: float
    long: float
    structure: str
    vector: list[float]
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class STO3LayerEngine:
    """Three-layer oscillator engine for ADE v2.

    Uses weekly data and returns short/middle/long stochastic values.
    """

    FEATURE_NAMES = ["sto_short", "sto_middle", "sto_long", "sto_spread", "sto_slope"]

    def extract(self, data: pd.DataFrame) -> STOLayers:
        weekly = self._to_weekly(data)
        if len(weekly) < 10:
            return STOLayers(50, 50, 50, "STO_UNKNOWN", [0.5, 0.5, 0.5, 0, 0], ["sto_unknown"])
        short_series = self._stochastic(weekly, 5)
        middle_series = self._stochastic(weekly, 14)
        long_series = self._stochastic(weekly, 34)
        short = self._safe(short_series.iloc[-1])
        middle = self._safe(middle_series.iloc[-1])
        long = self._safe(long_series.iloc[-1])
        prev_short = self._safe(short_series.iloc[-2]) if len(short_series) >= 2 else short
        slope = (short - prev_short) / 100
        spread = (short - long) / 100
        if short >= middle >= long and short >= 55:
            structure = "STO_3LAYER_UP"
            labels = ["sto_3layer_up"]
        elif short >= middle:
            structure = "STO_TURN_UP"
            labels = ["sto_turn_up"]
        elif short <= middle <= long and short <= 45:
            structure = "STO_3LAYER_DOWN"
            labels = ["sto_3layer_down"]
        else:
            structure = "STO_MIXED"
            labels = ["sto_mixed"]
        vector = [round(short / 100, 6), round(middle / 100, 6), round(long / 100, 6), round(spread, 6), round(slope, 6)]
        return STOLayers(round(short, 4), round(middle, 4), round(long, 4), structure, vector, labels)

    @staticmethod
    def similarity(a: STOLayers, b: STOLayers) -> float:
        distance = sum((x - y) ** 2 for x, y in zip(a.vector, b.vector)) ** 0.5
        return round(max(0.0, 100.0 / (1.0 + distance)), 2)

    @staticmethod
    def _stochastic(df: pd.DataFrame, period: int) -> pd.Series:
        low = df["Low"].rolling(period, min_periods=max(3, period // 3)).min()
        high = df["High"].rolling(period, min_periods=max(3, period // 3)).max()
        return ((df["Close"] - low) / (high - low).replace(0, pd.NA) * 100).fillna(50)

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
    def _safe(value: float) -> float:
        return 50.0 if pd.isna(value) else float(value)
