from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EnvironmentSnapshot:
    rate: float | None = None
    dxy: float | None = None
    vix: float | None = None
    liquidity: float | None = None
    nasdaq_trend: float | None = None
    sector_trend: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class EnvironmentEngine:
    """Manual environment synchronization v1.

    Later this will be connected to external macro data. For now it accepts manual inputs
    and converts them into an explainable 0-100 environment score.
    """

    def score(self, snapshot: EnvironmentSnapshot | None = None) -> int:
        if snapshot is None:
            return 70

        scores: list[float] = []
        if snapshot.vix is not None:
            scores.append(90 if snapshot.vix < 16 else 75 if snapshot.vix < 22 else 55 if snapshot.vix < 30 else 30)
        if snapshot.dxy is not None:
            scores.append(80 if snapshot.dxy < 103 else 65 if snapshot.dxy < 106 else 45)
        if snapshot.rate is not None:
            scores.append(80 if snapshot.rate < 4.0 else 65 if snapshot.rate < 5.0 else 45)
        if snapshot.liquidity is not None:
            scores.append(80 if snapshot.liquidity > 0 else 50)
        if snapshot.nasdaq_trend is not None:
            scores.append(85 if snapshot.nasdaq_trend > 0 else 45)
        if snapshot.sector_trend is not None:
            scores.append(85 if snapshot.sector_trend > 0 else 45)

        if not scores:
            return 70
        return round(sum(scores) / len(scores))
