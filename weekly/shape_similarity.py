from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class WeeklyShape:
    normalized_close: list[float]
    normalized_high: list[float]
    normalized_low: list[float]
    volume_ratio: list[float]
    box_width: float
    pullback_depth: float
    breakout_angle: float
    trend_slope: float
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class WeeklyShapeSimilarityEngine:
    """Compare weekly chart shape, not only category labels."""

    def __init__(self, weeks: int = 26) -> None:
        self.weeks = weeks

    def extract(self, data: pd.DataFrame) -> WeeklyShape:
        weekly = self._to_weekly(data).tail(self.weeks).reset_index(drop=True)
        if weekly.empty:
            return WeeklyShape([], [], [], [], 0, 0, 0, 0, ["weekly_shape_empty"])

        close = pd.to_numeric(weekly["Close"], errors="coerce").astype(float)
        high = pd.to_numeric(weekly["High"], errors="coerce").astype(float)
        low = pd.to_numeric(weekly["Low"], errors="coerce").astype(float)
        volume = pd.to_numeric(weekly["Volume"], errors="coerce").astype(float)
        base = float(close.iloc[0]) if float(close.iloc[0]) != 0 else 1.0

        normalized_close = ((close / base) - 1).clip(-1.0, 3.0).round(6).tolist()
        normalized_high = ((high / base) - 1).clip(-1.0, 3.0).round(6).tolist()
        normalized_low = ((low / base) - 1).clip(-1.0, 3.0).round(6).tolist()

        vol_ma = volume.rolling(8, min_periods=2).mean()
        safe_vol_ma = vol_ma.where(vol_ma != 0)
        volume_ratio = pd.to_numeric(volume.div(safe_vol_ma), errors="coerce").fillna(1.0).clip(0, 10).round(6).tolist()

        prior = weekly.iloc[:-1] if len(weekly) > 1 else weekly
        high_max = float(prior["High"].max()) if not prior.empty else float(high.max())
        low_min = float(prior["Low"].min()) if not prior.empty else float(low.min())
        box_width = 0.0 if low_min <= 0 else min(2.0, (high_max - low_min) / low_min)

        recent_high = float(high.max())
        latest = float(close.iloc[-1])
        pullback_depth = 0.0 if recent_high <= 0 else min(1.0, max(0.0, (recent_high - latest) / recent_high))
        breakout_angle = 0.0
        if len(close) >= 4 and high_max > 0:
            breakout_angle = max(-1.0, min(1.0, (latest - float(close.iloc[-4])) / high_max))
        trend_slope = 0.0
        if len(close) >= 8 and base > 0:
            trend_slope = max(-1.0, min(1.0, (float(close.iloc[-1]) - float(close.iloc[-8])) / base))

        labels: list[str] = []
        if latest >= high_max * 0.97:
            labels.append("near_breakout")
        if pullback_depth >= 0.08:
            labels.append("pullback")
        if box_width <= 0.35:
            labels.append("tight_box")
        if trend_slope > 0:
            labels.append("up_slope")

        return WeeklyShape(
            normalized_close=normalized_close,
            normalized_high=normalized_high,
            normalized_low=normalized_low,
            volume_ratio=volume_ratio,
            box_width=round(box_width, 6),
            pullback_depth=round(pullback_depth, 6),
            breakout_angle=round(breakout_angle, 6),
            trend_slope=round(trend_slope, 6),
            labels=labels,
        )

    def similarity(self, a: WeeklyShape, b: WeeklyShape) -> float:
        if not a.normalized_close or not b.normalized_close:
            return 0.0
        close_score = self._path_similarity(a.normalized_close, b.normalized_close)
        high_score = self._path_similarity(a.normalized_high, b.normalized_high)
        low_score = self._path_similarity(a.normalized_low, b.normalized_low)
        volume_score = self._path_similarity(a.volume_ratio, b.volume_ratio)
        structure_score = self._feature_similarity(
            [a.box_width, a.pullback_depth, a.breakout_angle, a.trend_slope],
            [b.box_width, b.pullback_depth, b.breakout_angle, b.trend_slope],
        )
        return round(close_score * 0.35 + high_score * 0.10 + low_score * 0.10 + volume_score * 0.15 + structure_score * 0.30, 2)

    @staticmethod
    def _path_similarity(a: list[float], b: list[float]) -> float:
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        aa = a[-n:]
        bb = b[-n:]
        rmse = (sum((x - y) ** 2 for x, y in zip(aa, bb)) / n) ** 0.5
        return max(0.0, 100.0 / (1.0 + rmse * 3.0))

    @staticmethod
    def _feature_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        distance = sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
        return max(0.0, 100.0 / (1.0 + distance * 2.0))

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
