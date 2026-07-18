from __future__ import annotations

from dataclasses import asdict, dataclass, field

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
    # Backward-compatible fields. Old stored patterns without these arrays can
    # still be loaded, but new patterns compare the recent STO curve itself.
    short_path: list[float] = field(default_factory=list)
    middle_path: list[float] = field(default_factory=list)
    long_path: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class STOStructureSimilarityEngine:
    """Compare the recent three-layer weekly STO structure.

    The visual reference compares three weekly STO curves around the turning
    point, not just one terminal value. The engine therefore compares the last
    six weekly observations of these layers:

    * short  : STO (5, 3, 3)
    * middle : STO (10, 6, 6)
    * long   : STO (20, 12, 12)

    Terminal arrangement, convergence and direction remain supporting
    features, while the recent curve trajectory is the main similarity input.
    """

    PATH_WEEKS = 6

    def __init__(self) -> None:
        self.layer_engine = STO3LayerEngine()

    def extract(self, data: pd.DataFrame) -> STOStructure:
        weekly = self.layer_engine._to_weekly(data)
        if len(weekly) < 10:
            neutral_path = [0.5] * self.PATH_WEEKS
            return STOStructure(
                50, 50, 50, 0, 0, 1, 0, 0, 0, "UNKNOWN",
                [0.5, 0.5, 0.5, 0, 0, 1, 0, 0, 0],
                ["sto_unknown"],
                neutral_path, neutral_path, neutral_path,
            )

        short_series = self._smoothed_stochastic(weekly, 5, 3, 3)
        middle_series = self._smoothed_stochastic(weekly, 10, 6, 6)
        long_series = self._smoothed_stochastic(weekly, 20, 12, 12)

        short_path = self._normalized_tail(short_series, self.PATH_WEEKS)
        middle_path = self._normalized_tail(middle_series, self.PATH_WEEKS)
        long_path = self._normalized_tail(long_series, self.PATH_WEEKS)

        short = short_path[-1] * 100
        middle = middle_path[-1] * 100
        long = long_path[-1] * 100
        prev_s = short_path[-2] * 100 if len(short_path) >= 2 else short
        prev_m = middle_path[-2] * 100 if len(middle_path) >= 2 else middle
        prev_l = long_path[-2] * 100 if len(long_path) >= 2 else long

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
        if self._turned_up(short_path):
            labels.append("short_turning_up")
        if self._turned_up(middle_path):
            labels.append("middle_turning_up")
        if self._turned_up(long_path):
            labels.append("long_turning_up")

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
            short_path=[round(float(v), 6) for v in short_path],
            middle_path=[round(float(v), 6) for v in middle_path],
            long_path=[round(float(v), 6) for v in long_path],
        )

    def similarity(self, a: STOStructure, b: STOStructure) -> float:
        if self._has_paths(a) and self._has_paths(b):
            short_curve = self._path_similarity(a.short_path, b.short_path)
            middle_curve = self._path_similarity(a.middle_path, b.middle_path)
            long_curve = self._path_similarity(a.long_path, b.long_path)
            trajectory_score = short_curve * 0.40 + middle_curve * 0.35 + long_curve * 0.25
        else:
            # Compatibility for patterns stored before trajectory arrays existed.
            trajectory_score = self._feature_similarity(a.vector[0:3], b.vector[0:3], scale=2.0)

        structure_score = self._feature_similarity(a.vector[3:6], b.vector[3:6], scale=3.0)
        slope_score = self._feature_similarity(a.vector[6:9], b.vector[6:9], scale=6.0)
        arrangement_score = (
            100.0 if a.arrangement == b.arrangement
            else 55.0 if self._compatible(a.arrangement, b.arrangement)
            else 25.0
        )

        # The curve shape visible in the chart is now the main criterion.
        return round(
            trajectory_score * 0.55
            + arrangement_score * 0.20
            + structure_score * 0.15
            + slope_score * 0.10,
            2,
        )

    @staticmethod
    def _smoothed_stochastic(df: pd.DataFrame, period: int, k_smooth: int, d_smooth: int) -> pd.Series:
        raw = STO3LayerEngine._stochastic(df, period)
        slow_k = raw.rolling(k_smooth, min_periods=1).mean()
        return slow_k.rolling(d_smooth, min_periods=1).mean().fillna(50)

    @staticmethod
    def _normalized_tail(series: pd.Series, length: int) -> list[float]:
        values = [max(0.0, min(100.0, float(value))) / 100 for value in series.tail(length).tolist()]
        if not values:
            return [0.5] * length
        if len(values) < length:
            values = [values[0]] * (length - len(values)) + values
        return values

    @staticmethod
    def _turned_up(path: list[float]) -> bool:
        return len(path) >= 3 and path[-3] >= path[-2] and path[-1] > path[-2]

    @staticmethod
    def _has_paths(value: STOStructure) -> bool:
        return bool(value.short_path and value.middle_path and value.long_path)

    @staticmethod
    def _path_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        # Compare both absolute oscillator position and curve direction.
        level_distance = (sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)) ** 0.5
        a_changes = [a[index] - a[index - 1] for index in range(1, len(a))]
        b_changes = [b[index] - b[index - 1] for index in range(1, len(b))]
        direction_distance = (
            sum((x - y) ** 2 for x, y in zip(a_changes, b_changes)) / max(1, len(a_changes))
        ) ** 0.5
        distance = level_distance * 0.55 + direction_distance * 0.45
        return max(0.0, 100.0 / (1.0 + distance * 5.0))

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
