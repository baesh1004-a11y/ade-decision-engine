from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from pattern.vector import PatternVector, PatternVectorizer


ENGINE_VERSION = "pattern-matching-v1.0.0"


@dataclass(frozen=True)
class PatternMatch:
    ticker: str
    end_index: int
    similarity: float
    close: float
    forward_returns: dict[str, float]


@dataclass(frozen=True)
class PatternMatchDecision:
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


class PatternMatchingEngine:
    """Find historical windows similar to the current chart pattern.

    v1.0 uses in-memory brute-force cosine similarity. This is intentionally
    simple and deterministic. v2.0 can replace the search backend with a vector DB.
    """

    def __init__(self, window: int = 20, top_k: int = 10, horizons: tuple[int, ...] = (5, 10, 20, 40)) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        self.window = window
        self.top_k = top_k
        self.horizons = horizons
        self.vectorizer = PatternVectorizer(window=window)

    def evaluate(self, df: pd.DataFrame, ticker: str = "UNKNOWN") -> PatternMatchDecision:
        self._validate(df)
        latest = self.vectorizer.transform_latest(df, ticker=ticker)
        candidates = self._historical_candidates(df, ticker=ticker)
        matches = self._rank_matches(latest, candidates, df)
        top_matches = matches[: self.top_k]

        expected_returns = self._avg_forward_returns(top_matches)
        win_rates = self._win_rates(top_matches)
        avg_similarity = float(np.mean([m.similarity for m in top_matches])) if top_matches else 0.0
        flags = self._risk_flags(top_matches, expected_returns, avg_similarity)
        reasons = self._reasons(top_matches, expected_returns, avg_similarity, flags)

        return PatternMatchDecision(
            engine_version=ENGINE_VERSION,
            ticker=ticker,
            window=self.window,
            top_k=self.top_k,
            match_count=len(top_matches),
            avg_similarity=round(avg_similarity, 4),
            expected_returns={k: round(v, 4) for k, v in expected_returns.items()},
            win_rates={k: round(v, 4) for k, v in win_rates.items()},
            risk_flags=flags,
            matches=[asdict(match) for match in top_matches],
            reasons=reasons,
        )

    def _validate(self, df: pd.DataFrame) -> None:
        required = {"Open", "High", "Low", "Close", "Volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Pattern matching requires columns: {', '.join(sorted(missing))}")
        min_len = self.window + max(self.horizons) + 1
        if len(df) < min_len:
            raise ValueError(f"Pattern matching requires at least {min_len} rows")

    def _historical_candidates(self, df: pd.DataFrame, ticker: str) -> list[PatternVector]:
        latest_index = len(df) - 1
        max_forward = max(self.horizons)
        last_candidate_index = latest_index - max_forward
        if last_candidate_index < self.window - 1:
            return []
        return [
            self.vectorizer.transform_window(df, end_index=i, ticker=ticker)
            for i in range(self.window - 1, last_candidate_index + 1)
        ]

    def _rank_matches(
        self,
        latest: PatternVector,
        candidates: list[PatternVector],
        df: pd.DataFrame,
    ) -> list[PatternMatch]:
        ranked: list[PatternMatch] = []
        latest_arr = np.asarray(latest.values, dtype=float)
        for candidate in candidates:
            cand_arr = np.asarray(candidate.values, dtype=float)
            similarity = self._cosine_similarity(latest_arr, cand_arr)
            close = float(df.iloc[candidate.end_index]["Close"])
            ranked.append(
                PatternMatch(
                    ticker=candidate.ticker,
                    end_index=candidate.end_index,
                    similarity=round(similarity, 6),
                    close=close,
                    forward_returns=self._forward_returns(df, candidate.end_index),
                )
            )
        return sorted(ranked, key=lambda item: item.similarity, reverse=True)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def _forward_returns(self, df: pd.DataFrame, end_index: int) -> dict[str, float]:
        base = float(df.iloc[end_index]["Close"])
        returns: dict[str, float] = {}
        for horizon in self.horizons:
            future_index = end_index + horizon
            if future_index >= len(df) or base <= 0:
                continue
            future_close = float(df.iloc[future_index]["Close"])
            returns[f"return_{horizon}d"] = (future_close - base) / base
        return returns

    def _avg_forward_returns(self, matches: list[PatternMatch]) -> dict[str, float]:
        result: dict[str, float] = {}
        for horizon in self.horizons:
            key = f"return_{horizon}d"
            vals = [match.forward_returns[key] for match in matches if key in match.forward_returns]
            result[key] = float(np.mean(vals)) if vals else 0.0
        return result

    def _win_rates(self, matches: list[PatternMatch]) -> dict[str, float]:
        result: dict[str, float] = {}
        for horizon in self.horizons:
            key = f"return_{horizon}d"
            vals = [match.forward_returns[key] for match in matches if key in match.forward_returns]
            result[f"win_rate_{horizon}d"] = sum(v > 0 for v in vals) / len(vals) if vals else 0.0
        return result

    def _risk_flags(self, matches: list[PatternMatch], expected: dict[str, float], avg_similarity: float) -> list[str]:
        flags: list[str] = []
        if len(matches) < max(3, self.top_k // 2):
            flags.append("Insufficient similar samples")
        if avg_similarity < 0.70:
            flags.append("Low pattern similarity")
        if expected.get("return_20d", 0.0) < 0:
            flags.append("Negative 20-day expected return")
        return flags

    def _reasons(
        self,
        matches: list[PatternMatch],
        expected: dict[str, float],
        avg_similarity: float,
        flags: list[str],
    ) -> list[str]:
        reasons = [
            f"Found {len(matches)} historical similar patterns",
            f"Average similarity is {avg_similarity:.2%}",
        ]
        if "return_20d" in expected:
            reasons.append(f"Average 20-day forward return is {expected['return_20d']:.2%}")
        if flags:
            reasons.append("Pattern evidence requires caution")
        return reasons


def evaluate_pattern_match(
    df: pd.DataFrame,
    ticker: str = "UNKNOWN",
    window: int = 20,
    top_k: int = 10,
    horizons: tuple[int, ...] = (5, 10, 20, 40),
) -> dict[str, Any]:
    return PatternMatchingEngine(window=window, top_k=top_k, horizons=horizons).evaluate(df, ticker=ticker).to_dict()
