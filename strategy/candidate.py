from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


ENGINE_VERSION = "candidate-v0.2.0"


@dataclass(frozen=True)
class RuleHit:
    """A transparent scoring contribution from one decision rule."""

    name: str
    points: int
    reason: str


@dataclass(frozen=True)
class CandidateDecision:
    """Serializable decision record for one ticker/date snapshot."""

    engine_version: str
    score: int
    grade: str
    action: str
    confidence: float
    close: float
    risk_level: str
    risk_flags: list[str]
    reasons: list[str]
    rule_hits: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_float(row: pd.Series, key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    if pd.isna(value):
        return default
    return float(value)


def _safe_bool(row: pd.Series, key: str, default: bool = False) -> bool:
    value = row.get(key, default)
    if pd.isna(value):
        return default
    return bool(value)


def _grade(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _action(score: int, risk_level: str) -> str:
    if risk_level == "HIGH":
        return "WATCH"
    if score >= 85:
        return "BUY_CANDIDATE"
    if score >= 70:
        return "WATCHLIST"
    if score >= 55:
        return "NEUTRAL"
    return "REJECT"


def _risk_flags(row: pd.Series) -> list[str]:
    flags: list[str] = []
    close = _safe_float(row, "Close")
    ma120 = _safe_float(row, "MA120")
    vol20_ratio = _safe_float(row, "VOL20_RATIO")
    sto533_k = _safe_float(row, "STO533_K", 100.0)
    body_ratio = _safe_float(row, "BODY_RATIO")
    is_bullish = _safe_bool(row, "IS_BULLISH")

    if close > 0 and ma120 > 0 and close < ma120:
        flags.append("Close below MA120")
    if vol20_ratio >= 15:
        flags.append("Abnormal volume spike")
    if sto533_k >= 85:
        flags.append("Short stochastic overheated")
    if not is_bullish and body_ratio >= 0.5:
        flags.append("Strong bearish candle body")

    return flags


def _risk_level(flags: list[str]) -> str:
    if any(flag in flags for flag in ["Strong bearish candle body", "Abnormal volume spike"]):
        return "HIGH"
    if flags:
        return "MEDIUM"
    return "LOW"


def evaluate_latest(df: pd.DataFrame) -> CandidateDecision:
    """Evaluate the latest row using ADE candidate decision engine v0.2.

    The engine is intentionally transparent. Each score contribution is retained
    in rule_hits so the decision can be audited and stored in a database.
    """
    if df.empty:
        raise ValueError("Cannot score an empty dataframe")

    row = df.iloc[-1]
    hits: list[RuleHit] = []

    vol20_ratio = _safe_float(row, "VOL20_RATIO")
    body_ratio = _safe_float(row, "BODY_RATIO")
    is_bullish = _safe_bool(row, "IS_BULLISH")
    sto533_k = _safe_float(row, "STO533_K", 100.0)
    sto533_d = _safe_float(row, "STO533_D")
    sto1066_k = _safe_float(row, "STO1066_K", 100.0)
    sto201212_k = _safe_float(row, "STO201212_K", 100.0)
    close = _safe_float(row, "Close")
    ma20 = _safe_float(row, "MA20")
    ma60 = _safe_float(row, "MA60")
    ma120 = _safe_float(row, "MA120")

    if vol20_ratio >= 2:
        hits.append(RuleHit("volume_2x", 15, "Volume is above 2x 20-day average"))
    if vol20_ratio >= 5:
        hits.append(RuleHit("volume_5x", 10, "Volume is above 5x 20-day average"))
    if vol20_ratio >= 10:
        hits.append(RuleHit("volume_10x", 10, "Volume is above 10x 20-day average"))

    if is_bullish and body_ratio >= 0.5:
        hits.append(RuleHit("bullish_body", 15, "Strong bullish candle body"))

    if sto533_k < 30 and sto533_k > sto533_d:
        hits.append(RuleHit("sto533_rebound", 15, "STO 5-3-3 early rebound signal"))
    if sto1066_k < 40:
        hits.append(RuleHit("sto1066_low", 10, "STO 10-6-6 is in low zone"))
    if sto201212_k < 50:
        hits.append(RuleHit("sto201212_safe", 10, "STO 20-12-12 is not overheated"))

    if close > 0 and ma120 > 0 and close >= ma120:
        hits.append(RuleHit("above_ma120", 10, "Close is above MA120"))
    if close > 0 and ma20 > ma60 > ma120 > 0:
        hits.append(RuleHit("ma_alignment", 10, "MA20 > MA60 > MA120 trend alignment"))
    if close > 0 and ma20 > 0 and close >= ma20:
        hits.append(RuleHit("above_ma20", 5, "Close is above MA20"))

    raw_score = sum(hit.points for hit in hits)
    score = min(raw_score, 100)
    flags = _risk_flags(row)
    risk = _risk_level(flags)
    grade = _grade(score)

    # Confidence is not prediction probability. It is an evidence-density score
    # based on how much of the rule book fired after risk gating.
    risk_penalty = {"LOW": 0.0, "MEDIUM": 0.15, "HIGH": 0.35}[risk]
    confidence = max(0.0, min(1.0, score / 100 - risk_penalty))

    return CandidateDecision(
        engine_version=ENGINE_VERSION,
        score=score,
        grade=grade,
        action=_action(score, risk),
        confidence=round(confidence, 4),
        close=close,
        risk_level=risk,
        risk_flags=flags,
        reasons=[hit.reason for hit in hits],
        rule_hits=[asdict(hit) for hit in hits],
    )


def score_latest(df: pd.DataFrame) -> dict[str, Any]:
    """Backward-compatible wrapper returning a dict decision payload."""
    return evaluate_latest(df).to_dict()
