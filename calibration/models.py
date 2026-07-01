from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ProbabilityObservation:
    ticker: str
    prediction_date: str
    horizon: str
    predicted_probability: float
    actual_outcome: int
    expected_return: float = 0.0
    realized_return: float = 0.0
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationBin:
    bin_start: float
    bin_end: float
    sample_count: int
    avg_predicted_probability: float
    observed_probability: float
    bias: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationTable:
    engine_version: str
    horizon: str
    sample_count: int
    bins: list[dict[str, Any]]
    global_bias: float
    brier_score: float
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
