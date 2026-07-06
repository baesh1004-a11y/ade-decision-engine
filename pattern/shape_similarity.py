from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class ShapeSimilarityResult:
    price_shape_score: float
    ma_shape_score: float
    volume_shape_score: float
    candle_body_score: float
    breakout_shape_score: float
    total_shape_score: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ShapeSimilarityEngine:
    """Compare actual chart shapes using DTW-like distance, not only state scores."""

    def compare(self, current: pd.DataFrame, historical: pd.DataFrame) -> ShapeSimilarityResult:
        cur = self._prepare(current)
        hist = self._prepare(historical)
        n = min(len(cur), len(hist))
        cur = cur.tail(n).reset_index(drop=True)
        hist = hist.tail(n).reset_index(drop=True)

        price_score = self._series_score(self._normalized_return(cur["Close"]), self._normalized_return(hist["Close"]))
        ma_score = self._series_score(self._ma_gap(cur), self._ma_gap(hist))
        volume_score = self._series_score(self._volume_ratio(cur), self._volume_ratio(hist))
        candle_score = self._series_score(self._candle_body(cur), self._candle_body(hist))
        breakout_score = self._series_score(self._breakout_position(cur), self._breakout_position(hist))

        total = round(
            price_score * 0.25
            + ma_score * 0.20
            + volume_score * 0.25
            + candle_score * 0.15
            + breakout_score * 0.15,
            1,
        )
        return ShapeSimilarityResult(
            price_shape_score=round(price_score, 1),
            ma_shape_score=round(ma_score, 1),
            volume_shape_score=round(volume_score, 1),
            candle_body_score=round(candle_score, 1),
            breakout_shape_score=round(breakout_score, 1),
            total_shape_score=total,
        )

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" in df.columns:
            df = df.sort_values("Date")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).reset_index(drop=True)

    @staticmethod
    def _normalized_return(series: pd.Series) -> list[float]:
        values = pd.to_numeric(series, errors="coerce").dropna().astype(float)
        if values.empty or float(values.iloc[0]) <= 0:
            return []
        return ((values / float(values.iloc[0])) - 1.0).tolist()

    @staticmethod
    def _ma_gap(df: pd.DataFrame) -> list[float]:
        close = df["Close"].astype(float)
        ma20 = close.rolling(20, min_periods=5).mean()
        ma60 = close.rolling(60, min_periods=10).mean()
        gap = (ma20 - ma60) / close.replace(0, pd.NA)
        return gap.fillna(0).tolist()

    @staticmethod
    def _volume_ratio(df: pd.DataFrame) -> list[float]:
        volume = df["Volume"].astype(float)
        vol20 = volume.rolling(20, min_periods=5).mean().replace(0, pd.NA)
        ratio = (volume / vol20).clip(upper=10)
        return ratio.fillna(1).tolist()

    @staticmethod
    def _candle_body(df: pd.DataFrame) -> list[float]:
        high_low = (df["High"] - df["Low"]).replace(0, pd.NA)
        body = (df["Close"] - df["Open"]) / high_low
        return body.fillna(0).clip(lower=-3, upper=3).tolist()

    @staticmethod
    def _breakout_position(df: pd.DataFrame) -> list[float]:
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        close = df["Close"].astype(float)
        rolling_high = high.rolling(60, min_periods=10).max()
        rolling_low = low.rolling(60, min_periods=10).min()
        position = (close - rolling_low) / (rolling_high - rolling_low).replace(0, pd.NA)
        return position.fillna(0.5).clip(lower=0, upper=1.5).tolist()

    def _series_score(self, a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        distance = self._dtw_distance(a, b)
        normalized = distance / max(len(a), len(b))
        return max(0.0, min(100.0, 100.0 / (1.0 + normalized * 8.0)))

    @staticmethod
    def _dtw_distance(a: list[float], b: list[float]) -> float:
        n, m = len(a), len(b)
        prev = [float("inf")] * (m + 1)
        prev[0] = 0.0
        for i in range(1, n + 1):
            curr = [float("inf")] * (m + 1)
            for j in range(1, m + 1):
                cost = abs(a[i - 1] - b[j - 1])
                curr[j] = cost + min(curr[j - 1], prev[j], prev[j - 1])
            prev = curr
        return prev[m]
