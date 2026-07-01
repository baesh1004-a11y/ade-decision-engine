from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from pattern.memory import PatternMemoryMatch, PatternMemoryRepository
from pattern.vector import PatternVectorizer


ENGINE_VERSION = "pattern-memory-matching-v1.0.0"


@dataclass(frozen=True)
class PatternMemoryMatchDecision:
    engine_version: str
    ticker: str
    window: int
    top_k: int
    match_count: int
    avg_similarity: float
    expected_returns: dict[str, float]
    win_rates: dict[str, float]
    risk_flags: list[str]
    matches: list[dict[str, Any]]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PatternMemoryMatchingEngine:
    """Pattern matching backed by PatternMemoryRepository."""

    def __init__(
        self,
        repository: PatternMemoryRepository,
        window: int = 20,
        top_k: int = 10,
        horizons: tuple[int, ...] = (5, 10, 20, 40),
    ) -> None:
        self.repository = repository
        self.window = window
        self.top_k = top_k
        self.horizons = horizons
        self.vectorizer = PatternVectorizer(window=window)

    def evaluate(self, df: pd.DataFrame, market: str, ticker: str) -> PatternMemoryMatchDecision:
        latest = self.vectorizer.transform_latest(df, ticker=ticker)
        matches = self.repository.search(
            latest.values,
            top_k=self.top_k,
            market=market,
        )
        expected = self._avg_forward_returns(matches)
        win_rates = self._win_rates(matches)
        avg_similarity = float(np.mean([m.similarity for m in matches])) if matches else 0.0
        flags = self._risk_flags(matches, expected, avg_similarity)
        reasons = self._reasons(matches, expected, avg_similarity, flags)
        return PatternMemoryMatchDecision(
            engine_version=ENGINE_VERSION,
            ticker=ticker,
            window=self.window,
            top_k=self.top_k,
            match_count=len(matches),
            avg_similarity=round(avg_similarity, 4),
            expected_returns={key: round(value, 4) for key, value in expected.items()},
            win_rates={key: round(value, 4) for key, value in win_rates.items()},
            risk_flags=flags,
            matches=[match.to_dict() for match in matches],
            reasons=reasons,
        )

    def _avg_forward_returns(self, matches: list[PatternMemoryMatch]) -> dict[str, float]:
        result: dict[str, float] = {}
        for horizon in self.horizons:
            key = f"return_{horizon}d"
            vals = [float(match.forward_returns[key]) for match in matches if key in match.forward_returns]
            result[key] = float(np.mean(vals)) if vals else 0.0
        return result

    def _win_rates(self, matches: list[PatternMemoryMatch]) -> dict[str, float]:
        result: dict[str, float] = {}
        for horizon in self.horizons:
            key = f"return_{horizon}d"
            vals = [float(match.forward_returns[key]) for match in matches if key in match.forward_returns]
            result[f"win_rate_{horizon}d"] = sum(v > 0 for v in vals) / len(vals) if vals else 0.0
        return result

    def _risk_flags(self, matches: list[PatternMemoryMatch], expected: dict[str, float], avg_similarity: float) -> list[str]:
        flags: list[str] = []
        if len(matches) < max(3, self.top_k // 2):
            flags.append("Insufficient memory samples")
        if avg_similarity < 0.70:
            flags.append("Low memory pattern similarity")
        if expected.get("return_20d", 0.0) < 0:
            flags.append("Negative memory-based 20-day expected return")
        return flags

    def _reasons(
        self,
        matches: list[PatternMemoryMatch],
        expected: dict[str, float],
        avg_similarity: float,
        flags: list[str],
    ) -> list[str]:
        reasons = [
            f"Found {len(matches)} memory-backed similar patterns",
            f"Average memory similarity is {avg_similarity:.2%}",
        ]
        if "return_20d" in expected:
            reasons.append(f"Memory-based 20-day expected return is {expected['return_20d']:.2%}")
        if flags:
            reasons.append("Memory evidence requires caution")
        return reasons
