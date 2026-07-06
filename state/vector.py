from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from centerline.engine import CenterlineEngine


@dataclass(frozen=True)
class ADEStateVector:
    vector: list[float]
    feature_names: list[str]
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ADEStateVectorEngine:
    FEATURE_NAMES = [
        "amount_ratio_20d",
        "amount_ratio_120d",
        "amount_change_5d",
        "rsi5",
        "rsi10",
        "rsi20",
        "rsi_gap",
        "ma5_slope",
        "ma20_slope",
        "ma60_slope",
        "ma_alignment",
        "price_position_120d",
        "year_center_distance",
        "box_range_120d",
        "candle_body_strength",
        "volatility_20d",
    ]

    def __init__(self) -> None:
        self.centerline_engine = CenterlineEngine()

    def extract(self, data: pd.DataFrame) -> ADEStateVector:
        df = self._prepare(data)
        close = df["Close"]
        open_ = df["Open"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]
        amount = close * volume

        amount_ratio_20 = self._ratio(amount.iloc[-1], amount.rolling(20, min_periods=5).mean().iloc[-1], 20)
        amount_ratio_120 = self._ratio(amount.iloc[-1], amount.rolling(120, min_periods=20).mean().iloc[-1], 30)
        prev_amount = amount.iloc[-6] if len(amount) >= 6 else amount.iloc[0]
        amount_change_5d = self._clip((amount.iloc[-1] / prev_amount - 1) if prev_amount else 0, -1, 5) / 5

        rsi5 = self._rsi(close, 5).iloc[-1]
        rsi10 = self._rsi(close, 10).iloc[-1]
        rsi20 = self._rsi(close, 20).iloc[-1]
        rsi_gap = self._clip((self._safe(rsi5) - self._safe(rsi20)) / 100, -1, 1)

        ma5 = close.rolling(5, min_periods=3).mean()
        ma20 = close.rolling(20, min_periods=5).mean()
        ma60 = close.rolling(60, min_periods=20).mean()
        latest = float(close.iloc[-1])
        ma_alignment = 1.0 if latest > ma5.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1] else 0.7 if latest > ma20.iloc[-1] > ma60.iloc[-1] else 0.35 if latest > ma20.iloc[-1] else 0.0

        rolling_high = high.rolling(120, min_periods=20).max().iloc[-1]
        rolling_low = low.rolling(120, min_periods=20).min().iloc[-1]
        price_position = 0.5 if rolling_high == rolling_low else self._clip((latest - rolling_low) / (rolling_high - rolling_low), 0, 1.5) / 1.5
        box_range = 1.0 if not rolling_low else self._clip((rolling_high - rolling_low) / rolling_low, 0, 2) / 2

        center = self.centerline_engine.snapshot(df)
        year_center_distance = 0.0 if not center.yearly else self._clip((latest / center.yearly - 1), -0.5, 1.0)
        candle_range = max(float(high.iloc[-1] - low.iloc[-1]), 1e-9)
        body_strength = self._clip((float(close.iloc[-1] - open_.iloc[-1]) / candle_range + 1) / 2, 0, 1)
        vol = close.pct_change().rolling(20, min_periods=5).std().iloc[-1]
        volatility = self._clip(float(vol) if pd.notna(vol) else 0, 0, 0.12) / 0.12

        vector = [
            amount_ratio_20 / 20,
            amount_ratio_120 / 30,
            amount_change_5d,
            self._safe(rsi5) / 100,
            self._safe(rsi10) / 100,
            self._safe(rsi20) / 100,
            rsi_gap,
            self._slope(ma5, close),
            self._slope(ma20, close),
            self._slope(ma60, close),
            ma_alignment,
            price_position,
            year_center_distance,
            box_range,
            body_strength,
            volatility,
        ]
        labels = self._labels(vector)
        return ADEStateVector([round(float(v), 6) for v in vector], list(self.FEATURE_NAMES), labels)

    @staticmethod
    def similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        distance = sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
        return round(max(0.0, 100.0 / (1.0 + distance)), 2)

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" in df.columns:
            df = df.sort_values("Date")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).reset_index(drop=True)

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period, min_periods=3).mean()
        loss = (-delta.clip(upper=0)).rolling(period, min_periods=3).mean().replace(0, pd.NA)
        return (100 - (100 / (1 + gain / loss))).fillna(50)

    @staticmethod
    def _ratio(value: float, base: float, cap: float) -> float:
        if not base or pd.isna(base):
            return 1.0
        return max(0.0, min(cap, float(value) / float(base)))

    @staticmethod
    def _slope(ma: pd.Series, close: pd.Series) -> float:
        if len(ma) < 6 or pd.isna(ma.iloc[-1]) or pd.isna(ma.iloc[-6]) or close.iloc[-1] == 0:
            return 0.0
        return max(-1.0, min(1.0, float((ma.iloc[-1] - ma.iloc[-6]) / close.iloc[-1]) * 10))

    @staticmethod
    def _clip(value: float, low: float, high: float) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _safe(value: float) -> float:
        return 50.0 if pd.isna(value) else float(value)

    @staticmethod
    def _labels(vector: list[float]) -> list[str]:
        labels: list[str] = []
        if vector[1] >= 10 / 30:
            labels.append("대금상승")
        if vector[6] > 0.15:
            labels.append("STO상승구조")
        if vector[10] >= 0.7:
            labels.append("이평우상향")
        if vector[11] >= 0.55:
            labels.append("주봉상단권")
        if vector[12] >= 0:
            labels.append("연봉중심값상단")
        return labels
