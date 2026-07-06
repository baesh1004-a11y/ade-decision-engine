from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from centerline.engine import CenterlineEngine
from sto.layer_engine import STO3LayerEngine
from weekly.pattern import WeeklyPatternEngine


@dataclass(frozen=True)
class ADEStateVector:
    vector: list[float]
    feature_names: list[str]
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ADEStateVectorEngine:
    """ADE v2 state vector.

    Core similarity is weekly chart structure + STO 3-layer structure.
    Money and centerline are context features only.
    """

    FEATURE_NAMES = [
        "weekly_position",
        "weekly_trend",
        "weekly_box",
        "weekly_breakout",
        "weekly_pullback",
        "sto_short",
        "sto_middle",
        "sto_long",
        "sto_spread",
        "sto_slope",
        "amount_ratio_20d",
        "amount_ratio_120d",
        "amount_change_5d",
        "year_center_distance",
        "box_range_120d",
        "candle_body_strength",
    ]

    def __init__(self) -> None:
        self.centerline_engine = CenterlineEngine()
        self.weekly_engine = WeeklyPatternEngine()
        self.sto_engine = STO3LayerEngine()

    def extract(self, data: pd.DataFrame) -> ADEStateVector:
        df = self._prepare(data)
        close = df["Close"]
        open_ = df["Open"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]
        amount = close * volume

        weekly = self.weekly_engine.extract(df)
        sto = self.sto_engine.extract(df)

        amount_ratio_20 = self._ratio(amount.iloc[-1], amount.rolling(20, min_periods=5).mean().iloc[-1], 20)
        amount_ratio_120 = self._ratio(amount.iloc[-1], amount.rolling(120, min_periods=20).mean().iloc[-1], 30)
        prev_amount = amount.iloc[-6] if len(amount) >= 6 else amount.iloc[0]
        amount_change_5d = self._clip((amount.iloc[-1] / prev_amount - 1) if prev_amount else 0, -1, 5) / 5

        latest = float(close.iloc[-1])
        rolling_high = high.rolling(120, min_periods=20).max().iloc[-1]
        rolling_low = low.rolling(120, min_periods=20).min().iloc[-1]
        box_range = 1.0 if not rolling_low else self._clip((rolling_high - rolling_low) / rolling_low, 0, 2) / 2
        center = self.centerline_engine.snapshot(df)
        year_center_distance = 0.0 if not center.yearly else self._clip((latest / center.yearly - 1), -0.5, 1.0)
        candle_range = max(float(high.iloc[-1] - low.iloc[-1]), 1e-9)
        body_strength = self._clip((float(close.iloc[-1] - open_.iloc[-1]) / candle_range + 1) / 2, 0, 1)

        vector = [
            *weekly.vector,
            *sto.vector,
            amount_ratio_20 / 20,
            amount_ratio_120 / 30,
            amount_change_5d,
            year_center_distance,
            box_range,
            body_strength,
        ]
        labels = [*weekly.labels, *sto.labels, *self._context_labels(vector)]
        return ADEStateVector([round(float(v), 6) for v in vector], list(self.FEATURE_NAMES), labels)

    @staticmethod
    def similarity(a: list[float], b: list[float]) -> float:
        """Weighted similarity: weekly 40%, STO 40%, context 20%."""
        if not a or not b or len(a) != len(b):
            return 0.0
        weekly_distance = sum((a[i] - b[i]) ** 2 for i in range(0, 5)) ** 0.5
        sto_distance = sum((a[i] - b[i]) ** 2 for i in range(5, 10)) ** 0.5
        context_distance = sum((a[i] - b[i]) ** 2 for i in range(10, len(a))) ** 0.5
        weekly_score = 100.0 / (1.0 + weekly_distance)
        sto_score = 100.0 / (1.0 + sto_distance)
        context_score = 100.0 / (1.0 + context_distance)
        return round(weekly_score * 0.40 + sto_score * 0.40 + context_score * 0.20, 2)

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" in df.columns:
            df = df.sort_values("Date")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).reset_index(drop=True)

    @staticmethod
    def _ratio(value: float, base: float, cap: float) -> float:
        if not base or pd.isna(base):
            return 1.0
        return max(0.0, min(cap, float(value) / float(base)))

    @staticmethod
    def _clip(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _context_labels(vector: list[float]) -> list[str]:
        labels: list[str] = []
        if vector[11] >= 10 / 30:
            labels.append("amount_event")
        if vector[13] >= 0:
            labels.append("year_center_upper")
        return labels
