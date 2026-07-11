from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MetaScoreBreakdown:
    replay: float
    prediction: float
    jp_radar: float
    market: float
    sector: float
    risk: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class MetaScoreResult:
    rank: int
    market_code: str
    ticker: str
    name: str | None
    decision: str
    meta_score: float
    grade: str
    breakdown: MetaScoreBreakdown
    seven_day_up_probability: float | None
    seven_day_expected_return: float | None
    expected_peak_day: float | None
    target_return: float | None
    stop_return: float | None
    jp_radar_signal: str
    market_signal: str
    sector_signal: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["breakdown"] = self.breakdown.to_dict()
        return data
