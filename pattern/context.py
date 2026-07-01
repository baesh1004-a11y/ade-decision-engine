from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

import numpy as np
import pandas as pd

from pattern.matching import PatternMatchingEngine


ENGINE_VERSION = "pattern-context-v1.0.0"


class PatternEvidence(Protocol):
    avg_similarity: float
    expected_returns: dict[str, float]
    win_rates: dict[str, float]
    risk_flags: list[str]

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class PatternEvidenceAdapter:
    avg_similarity: float
    expected_returns: dict[str, float]
    win_rates: dict[str, float]
    risk_flags: list[str]
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class MarketContext:
    market_regime: str
    trend_score: float
    volume_score: float
    volatility_score: float
    vix_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatternContextDecision:
    engine_version: str
    ticker: str
    pattern_similarity: float
    context_similarity: float
    combined_similarity: float
    expected_returns: dict[str, float]
    win_rates: dict[str, float]
    risk_flags: list[str]
    reasons: list[str]
    pattern: dict[str, Any]
    current_context: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PatternContextEngine:
    """Combine chart-pattern evidence with market context similarity."""

    def __init__(self, window: int = 20, top_k: int = 10, horizons: tuple[int, ...] = (5, 10, 20, 40)) -> None:
        self.pattern_engine = PatternMatchingEngine(window=window, top_k=top_k, horizons=horizons)
        self.window = window
        self.top_k = top_k
        self.horizons = horizons

    def evaluate(
        self,
        df: pd.DataFrame,
        ticker: str = "UNKNOWN",
        market_regime: str = "SIDEWAY",
        vix: float | None = None,
    ) -> PatternContextDecision:
        pattern = self.pattern_engine.evaluate(df, ticker=ticker)
        return self.evaluate_from_pattern(
            df=df,
            pattern=pattern,
            ticker=ticker,
            market_regime=market_regime,
            vix=vix,
        )

    def evaluate_from_pattern(
        self,
        df: pd.DataFrame,
        pattern: PatternEvidence | dict[str, Any],
        ticker: str = "UNKNOWN",
        market_regime: str = "SIDEWAY",
        vix: float | None = None,
    ) -> PatternContextDecision:
        evidence = self._normalize_pattern(pattern)
        current_context = self._current_context(df, market_regime=market_regime, vix=vix)
        context_similarity = self._estimate_context_similarity(evidence, current_context)
        combined_similarity = self._combined_similarity(evidence.avg_similarity, context_similarity)
        expected = self._adjust_expected_returns(evidence.expected_returns, context_similarity)
        flags = self._risk_flags(evidence, context_similarity, combined_similarity, expected)
        reasons = self._reasons(evidence, current_context, context_similarity, combined_similarity, expected, flags)

        return PatternContextDecision(
            engine_version=ENGINE_VERSION,
            ticker=ticker,
            pattern_similarity=round(evidence.avg_similarity, 4),
            context_similarity=round(context_similarity, 4),
            combined_similarity=round(combined_similarity, 4),
            expected_returns={k: round(v, 4) for k, v in expected.items()},
            win_rates=evidence.win_rates,
            risk_flags=flags,
            reasons=reasons,
            pattern=evidence.to_dict(),
            current_context=current_context.to_dict(),
        )

    def _normalize_pattern(self, pattern: PatternEvidence | dict[str, Any]) -> PatternEvidence:
        if isinstance(pattern, dict):
            return PatternEvidenceAdapter(
                avg_similarity=float(pattern.get("avg_similarity", pattern.get("pattern_similarity", 0.0))),
                expected_returns=dict(pattern.get("expected_returns", {})),
                win_rates=dict(pattern.get("win_rates", {})),
                risk_flags=list(pattern.get("risk_flags", [])),
                payload=pattern,
            )
        return pattern

    def _current_context(self, df: pd.DataFrame, market_regime: str, vix: float | None) -> MarketContext:
        row = df.iloc[-1]
        close = self._safe_float(row, "Close")
        ma20 = self._safe_float(row, "MA20")
        ma60 = self._safe_float(row, "MA60")
        ma120 = self._safe_float(row, "MA120")
        vol_ratio = self._safe_float(row, "VOL20_RATIO", 1.0)

        trend_score = 0.5
        if close > ma20 > ma60 > ma120 > 0:
            trend_score = 1.0
        elif close > ma20 > 0:
            trend_score = 0.7
        elif ma120 > 0 and close < ma120:
            trend_score = 0.2

        volume_score = max(0.0, min(1.0, vol_ratio / 3.0))
        volatility_score = self._volatility_score(df)
        vix_score = self._vix_score(vix)

        return MarketContext(
            market_regime=market_regime.upper(),
            trend_score=round(trend_score, 4),
            volume_score=round(volume_score, 4),
            volatility_score=round(volatility_score, 4),
            vix_score=round(vix_score, 4),
        )

    def _estimate_context_similarity(self, pattern: PatternEvidence, context: MarketContext) -> float:
        base = 0.75
        if context.market_regime == "BULL":
            base += 0.08
        elif context.market_regime == "BEAR":
            base -= 0.12

        base += (context.trend_score - 0.5) * 0.20
        base += (context.volume_score - 0.5) * 0.10
        base -= max(0.0, context.volatility_score - 0.7) * 0.15
        base -= max(0.0, context.vix_score - 0.7) * 0.20

        low_similarity_flags = {"Low pattern similarity", "Low memory pattern similarity"}
        negative_flags = {"Negative 20-day expected return", "Negative memory-based 20-day expected return"}
        if any(flag in low_similarity_flags for flag in pattern.risk_flags):
            base -= 0.10
        if any(flag in negative_flags for flag in pattern.risk_flags):
            base -= 0.10

        return max(0.0, min(1.0, base))

    def _combined_similarity(self, pattern_similarity: float, context_similarity: float) -> float:
        return pattern_similarity * 0.70 + context_similarity * 0.30

    def _adjust_expected_returns(self, expected: dict[str, float], context_similarity: float) -> dict[str, float]:
        confidence_multiplier = 0.75 + context_similarity * 0.25
        return {key: value * confidence_multiplier for key, value in expected.items()}

    def _risk_flags(
        self,
        pattern: PatternEvidence,
        context_similarity: float,
        combined_similarity: float,
        expected: dict[str, float],
    ) -> list[str]:
        flags = list(pattern.risk_flags)
        if context_similarity < 0.60:
            flags.append("Low context similarity")
        if combined_similarity < 0.70:
            flags.append("Low combined pattern-context similarity")
        if expected.get("return_20d", 0.0) < 0:
            flags.append("Context-adjusted negative 20-day expected return")
        return flags

    def _reasons(
        self,
        pattern: PatternEvidence,
        context: MarketContext,
        context_similarity: float,
        combined_similarity: float,
        expected: dict[str, float],
        flags: list[str],
    ) -> list[str]:
        reasons = [
            f"Pattern similarity: {pattern.avg_similarity:.2%}",
            f"Context similarity: {context_similarity:.2%}",
            f"Combined similarity: {combined_similarity:.2%}",
            f"Market regime: {context.market_regime}",
        ]
        if "return_20d" in expected:
            reasons.append(f"Context-adjusted 20-day expected return: {expected['return_20d']:.2%}")
        if flags:
            reasons.append("Pattern-context evidence requires caution")
        return reasons

    def _volatility_score(self, df: pd.DataFrame) -> float:
        returns = df["Close"].astype(float).pct_change().tail(self.window).dropna()
        if returns.empty:
            return 0.5
        vol = float(returns.std())
        return max(0.0, min(1.0, vol / 0.04))

    def _vix_score(self, vix: float | None) -> float:
        if vix is None:
            return 0.5
        return max(0.0, min(1.0, float(vix) / 40.0))

    def _safe_float(self, row: pd.Series, key: str, default: float = 0.0) -> float:
        value = row.get(key, default)
        if pd.isna(value):
            return default
        return float(value)


def evaluate_pattern_context(
    df: pd.DataFrame,
    ticker: str = "UNKNOWN",
    market_regime: str = "SIDEWAY",
    vix: float | None = None,
    window: int = 20,
    top_k: int = 10,
    horizons: tuple[int, ...] = (5, 10, 20, 40),
) -> dict[str, Any]:
    return PatternContextEngine(window=window, top_k=top_k, horizons=horizons).evaluate(
        df=df,
        ticker=ticker,
        market_regime=market_regime,
        vix=vix,
    ).to_dict()
