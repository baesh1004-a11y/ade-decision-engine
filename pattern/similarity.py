from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


def cosine_similarity(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    """Return cosine similarity between two vectors."""
    av = np.asarray(a, dtype=float)
    bv = np.asarray(b, dtype=float)
    denominator = np.linalg.norm(av) * np.linalg.norm(bv)
    if denominator == 0:
        return 0.0
    return float(np.dot(av, bv) / denominator)


def euclidean_distance(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    """Return Euclidean distance between two vectors."""
    av = np.asarray(a, dtype=float)
    bv = np.asarray(b, dtype=float)
    return float(np.linalg.norm(av - bv))


def similarity_score(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    """Convert cosine similarity to 0-100 score."""
    score = cosine_similarity(a, b)
    return round(max(0.0, min(1.0, score)) * 100, 2)


@dataclass(frozen=True)
class SimilarPattern:
    start_date: str
    end_date: str
    similarity: float
    forward_return_20d: float | None
    current_points: list[float]
    historical_points: list[float]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PatternSimilarityEngine:
    """Find historical windows whose normalized price shape resembles the latest window."""

    def __init__(self, window: int = 30, forward_days: int = 20, min_gap: int = 20) -> None:
        self.window = window
        self.forward_days = forward_days
        self.min_gap = min_gap

    def find(self, data: pd.DataFrame, top_n: int = 3) -> list[SimilarPattern]:
        if len(data) < self.window * 2 + self.forward_days:
            return []

        df = data.copy().sort_values("Date").reset_index(drop=True)
        close = pd.to_numeric(df["Close"], errors="coerce")
        current = close.tail(self.window).reset_index(drop=True)
        current_shape = self._normalize(current)
        if current_shape is None:
            return []

        latest_start = len(df) - self.window
        candidates: list[SimilarPattern] = []
        for start in range(0, latest_start - self.min_gap):
            end = start + self.window
            if end + self.forward_days >= len(df):
                continue
            hist = close.iloc[start:end].reset_index(drop=True)
            hist_shape = self._normalize(hist)
            if hist_shape is None:
                continue
            similarity = self._shape_similarity(current_shape, hist_shape)
            entry = float(close.iloc[end - 1])
            exit_price = float(close.iloc[end + self.forward_days])
            forward_return = None if entry <= 0 else round((exit_price / entry - 1) * 100, 2)
            candidates.append(
                SimilarPattern(
                    start_date=str(pd.Timestamp(df.iloc[start]["Date"]).date()),
                    end_date=str(pd.Timestamp(df.iloc[end - 1]["Date"]).date()),
                    similarity=round(similarity, 2),
                    forward_return_20d=forward_return,
                    current_points=[round(float(x), 4) for x in current_shape],
                    historical_points=[round(float(x), 4) for x in hist_shape],
                )
            )

        return sorted(candidates, key=lambda item: item.similarity, reverse=True)[:top_n]

    @staticmethod
    def summary(matches: list[SimilarPattern]) -> dict[str, float | int | None]:
        returns = [m.forward_return_20d for m in matches if m.forward_return_20d is not None]
        if not returns:
            return {"matches": len(matches), "avg_forward_return_20d": None, "win_rate": None}
        return {
            "matches": len(returns),
            "avg_forward_return_20d": round(sum(returns) / len(returns), 2),
            "win_rate": round(sum(r > 0 for r in returns) / len(returns) * 100, 1),
        }

    @staticmethod
    def _normalize(series: pd.Series) -> list[float] | None:
        values = pd.to_numeric(series, errors="coerce").dropna().astype(float)
        if len(values) < 5:
            return None
        base = float(values.iloc[0])
        if base <= 0:
            return None
        normalized = values / base - 1.0
        return normalized.tolist()

    @staticmethod
    def _shape_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        mse = sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)
        return max(0.0, min(100.0, 100.0 * (1.0 - mse * 25.0)))
