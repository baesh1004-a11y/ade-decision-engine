from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from sto.layer_engine import STO3LayerEngine


@dataclass(frozen=True)
class STOStructure:
    short: float
    middle: float
    long: float
    spread_sm: float
    spread_ml: float
    convergence: float
    slope_short: float
    slope_middle: float
    slope_long: float
    arrangement: str
    vector: list[float]
    labels: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class STOStructureSimilarityEngine:
    """Compare STO 3-layer structure.

    It compares arrangement, convergence/divergence, slopes and level.
    """

    def __init__(self) -> None:
        self.layer_engine = STO3LayerEngine()

    def extract(self, data: pd.DataFrame) -> STOStructure:
        weekly = self.layer_engine._to_weekly(data)
        if len(weekly) < 10:
            return STOStructure(50, 50, 50, 0, 0, 1, 0, 0, 0, "UNKNOWN", [0.5, 0.5, 0.5, 0, 0, 1, 0, 0, 0], ["sto_unknown"])
        s = self.layer_engine._stochastic(weekly, 5)
        m = self.layer_engine._stochastic(weekly, 14)
        l = self.layer_engine._stochastic(weekly, 34)
        short = self._safe(s.iloc[-1])
        middle = self._safe(m.iloc[-1])
        long = self._safe(l.iloc[-1])
        prev_s = self._safe(s.iloc[-2]) if len(s) >= 2 else short
        prev_m = self._safe(m.iloc[-2]) if len(m) >= 2 else middle
        prev_l = self._safe(l.iloc[-2]) if len(l) >= 2 else long
        spread_sm = (short - middle) / 100
        spread_ml = (middle - long) / 100
        convergence = 1.0 - min(1.0, (max(short, middle, long) - min(short, middle, long)) / 100)
        slope_short = (short - prev_s) / 100
        slope_middle = (middle - prev_m) / 100
        slope_long = (long - prev_l) / 100

        if short >= middle >= long:
            arrangement = "UP_STACK"
        elif short <= middle <= long:
            arrangement = "DOWN_STACK"
        elif short >= middle and middle < long:
            arrangement = "SHORT_TURN_UP"
        elif short <= middle and middle > long:
            arrangement = "SHORT_TURN_DOWN"
        else:
            arrangement = "MIXED"

        labels: list[str] = [arrangement.lower()]
        if convergence >= 0.85:
            labels.append("converged")
        if spread_sm > 0 and spread_ml > 0:
            labels.append("diverging_up")
        if slope_short > 0 and slope_middle > 0 and slope_long > 0:
            labels.append("all_slopes_up")
        if slope_short < 0 and slope_middle < 0 and slope_long < 0:
            labels.append("all_slopes_down")

        vector = [
            short / 100,
            middle / 100,
            long / 100,
            spread_sm,
            spread_ml,
            convergence,
            slope_short,
            slope_middle,
            slope_long,
        ]
        return STOStructure(
            short=round(short, 4),
            middle=round(middle, 4),
            long=round(long, 4),
            spread_sm=round(spread_sm, 6),
            spread_ml=round(spread_ml, 6),
            convergence=round(convergence, 6),
            slope_short=round(slope_short, 6),
            slope_middle=round(slope_middle, 6),
            slope_long=round(slope_long, 6),
            arrangement=arrangement,
            vector=[round(float(v), 6) for v in vector],
            labels=labels,
        )

    def similarity(self, a: STOStructure, b: STOStructure) -> float:
        level_score = self._feature_similarity(a.vector[0:3], b.vector[0:3], scale=2.0)
        structure_score = self._feature_similarity(a.vector[3:6], b.vector[3:6], scale=3.0)
        slope_score = self._feature_similarity(a.vector[6:9], b.vector[6:9], scale=6.0)
        arrangement_score = 100.0 if a.arrangement == b.arrangement else 55.0 if self._compatible(a.arrangement, b.arrangement) else 25.0
        return round(arrangement_score * 0.35 + structure_score * 0.30 + slope_score * 0.20 + level_score * 0.15, 2)

    @staticmethod
    def _compatible(a: str, b: str) -> bool:
        up = {"UP_STACK", "SHORT_TURN_UP"}
        down = {"DOWN_STACK", "SHORT_TURN_DOWN"}
        return (a in up and b in up) or (a in down and b in down)

    @staticmethod
    def _feature_similarity(a: list[float], b: list[float], scale: float) -> float:
        if len(a) != len(b):
            return 0.0
        distance = sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
        return max(0.0, 100.0 / (1.0 + distance * scale))

    @staticmethod
    def _safe(value: float) -> float:
        return 50.0 if pd.isna(value) else float(value)
