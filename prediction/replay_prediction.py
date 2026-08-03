from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class HorizonPrediction:
    days: int
    sample_count: int
    up_probability: float
    expected_return: float
    median_return: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayPrediction:
    sample_count: int
    horizons: tuple[HorizonPrediction, ...]
    seven_day_up_probability: float
    seven_day_expected_return: float
    seven_day_median_return: float
    expected_max_return_7d: float
    expected_max_return_20d: float
    expected_peak_day: float
    expected_mdd_7d: float
    target_return: float
    stop_return: float
    holding_days: int
    grade: str

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["horizons"] = [item.to_dict() for item in self.horizons]
        return data


class ReplayPredictionEngine:
    """Estimate forward returns from matched Replay paths.

    Event metadata and future paths are cached in memory. Call ``preload`` once with
    the run's candidate event identifiers to avoid per-match SQLite queries.
    """

    HORIZONS = (3, 5, 7, 10, 20)

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._aliases: dict[str, tuple[str, ...]] = {}
        self._flow_cache: dict[str, tuple[tuple[int, float], ...]] = {}

    def close(self) -> None:
        self._aliases.clear()
        self._flow_cache.clear()
        self.conn.close()

    @staticmethod
    def _chunks(values: list[str], size: int = 800):
        for index in range(0, len(values), size):
            yield values[index:index + size]

    def preload(self, event_ids: Iterable[object]) -> None:
        requested = list(dict.fromkeys(str(value).strip() for value in event_ids if str(value or "").strip()))
        unresolved = [value for value in requested if value not in self._aliases]
        if unresolved:
            for chunk in self._chunks(unresolved):
                placeholders = ",".join("?" for _ in chunk)
                rows = self.conn.execute(
                    f"""
                    SELECT source_event_id, pattern_id
                    FROM surge_patterns
                    WHERE source_event_id IN ({placeholders}) OR pattern_id IN ({placeholders})
                    """,
                    (*chunk, *chunk),
                ).fetchall()
                for row in rows:
                    aliases = tuple(dict.fromkeys(
                        value for value in (
                            str(row["source_event_id"] or "").strip(),
                            str(row["pattern_id"] or "").strip(),
                        ) if value
                    ))
                    for alias in aliases:
                        self._aliases[alias] = aliases
            for value in unresolved:
                self._aliases.setdefault(value, (value,))

        needed_flows = list(dict.fromkeys(
            alias
            for value in requested
            for alias in self._aliases.get(value, (value,))
            if alias not in self._flow_cache
        ))
        for chunk in self._chunks(needed_flows):
            placeholders = ",".join("?" for _ in chunk)
            rows = self.conn.execute(
                f"""
                SELECT event_id, day_index, close
                FROM replay_event_flow
                WHERE event_id IN ({placeholders})
                ORDER BY event_id, day_index
                """,
                tuple(chunk),
            ).fetchall()
            grouped: dict[str, list[tuple[int, float]]] = {value: [] for value in chunk}
            for row in rows:
                grouped[str(row["event_id"])].append((int(row["day_index"]), float(row["close"] or 0.0)))
            for event_id, values in grouped.items():
                self._flow_cache[event_id] = tuple(values)

    def predict(self, replay_matches: Iterable[object]) -> ReplayPrediction | None:
        matches = list(replay_matches)
        self.preload(
            value
            for match in matches
            for value in (
                getattr(match, "source_event_id", None),
                getattr(match, "event_id", None),
                getattr(match, "pattern_id", None),
            )
        )

        samples: list[dict[str, object]] = []
        for match in matches:
            event_ids = self._event_ids(match)
            if not event_ids:
                continue
            future_week = int(getattr(match, "future_start_week_index", 0) or 0)
            similarity = float(getattr(match, "final_similarity", 0.0) or 0.0)
            sample = None
            for event_id in event_ids:
                sample = self._load_future_sample(event_id, future_week, similarity)
                if sample is not None:
                    break
            if sample is not None:
                samples.append(sample)

        if not samples:
            return None

        horizons = tuple(self._horizon_prediction(samples, days) for days in self.HORIZONS)
        seven = next(item for item in horizons if item.days == 7)
        max7 = self._weighted_mean(samples, "max_return_7d")
        max20 = self._weighted_mean(samples, "max_return_20d")
        peak_day = self._weighted_mean(samples, "peak_day_20d")
        mdd7 = self._weighted_mean(samples, "mdd_7d")

        target = round(max(0.0, median([float(s["max_return_7d"]) for s in samples])), 2)
        stop = round(min(0.0, median([float(s["mdd_7d"]) for s in samples])), 2)
        holding_days = max(1, int(round(peak_day)))
        grade = self._grade(seven.up_probability, seven.expected_return, max7, mdd7)

        return ReplayPrediction(
            sample_count=len(samples),
            horizons=horizons,
            seven_day_up_probability=seven.up_probability,
            seven_day_expected_return=seven.expected_return,
            seven_day_median_return=seven.median_return,
            expected_max_return_7d=round(max7, 2),
            expected_max_return_20d=round(max20, 2),
            expected_peak_day=round(peak_day, 1),
            expected_mdd_7d=round(mdd7, 2),
            target_return=target,
            stop_return=stop,
            holding_days=holding_days,
            grade=grade,
        )

    def _event_ids(self, match: object) -> list[str]:
        values = [
            getattr(match, "source_event_id", None),
            getattr(match, "event_id", None),
            getattr(match, "pattern_id", None),
        ]
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            for alias in self._aliases.get(text, (text,)):
                if alias not in result:
                    result.append(alias)
        return result

    def _load_future_sample(self, event_id: str, future_start_week_index: int, similarity: float) -> dict[str, object] | None:
        rows = self._flow_cache.get(event_id, ())
        if not rows:
            return None

        start_day = max(0, future_start_week_index * 5)
        future = [row for row in rows if row[0] >= start_day]
        if len(future) < 4:
            return None

        entry = float(future[0][1])
        if entry <= 0:
            return None

        closes = [float(row[1]) for row in future[:21]]
        returns = [(close / entry - 1.0) * 100.0 for close in closes]
        weight = max(0.01, similarity / 100.0)

        def ret_at(days: int) -> float:
            idx = min(days, len(returns) - 1)
            return returns[idx]

        window7 = returns[: min(8, len(returns))]
        window20 = returns[: min(21, len(returns))]
        peak_idx = max(range(len(window20)), key=lambda i: window20[i])

        return {
            "weight": weight,
            "ret_3d": ret_at(3),
            "ret_5d": ret_at(5),
            "ret_7d": ret_at(7),
            "ret_10d": ret_at(10),
            "ret_20d": ret_at(20),
            "max_return_7d": max(window7),
            "max_return_20d": max(window20),
            "peak_day_20d": float(peak_idx),
            "mdd_7d": min(window7),
        }

    def _horizon_prediction(self, samples: list[dict[str, object]], days: int) -> HorizonPrediction:
        key = f"ret_{days}d"
        values = [float(sample[key]) for sample in samples]
        weights = [float(sample["weight"]) for sample in samples]
        total_weight = sum(weights) or 1.0
        up_weight = sum(weight for value, weight in zip(values, weights) if value > 0)
        expected = sum(value * weight for value, weight in zip(values, weights)) / total_weight
        return HorizonPrediction(days=days, sample_count=len(values), up_probability=round(up_weight / total_weight * 100.0, 2), expected_return=round(expected, 2), median_return=round(median(values), 2))

    @staticmethod
    def _weighted_mean(samples: list[dict[str, object]], key: str) -> float:
        weights = [float(sample["weight"]) for sample in samples]
        total = sum(weights) or 1.0
        return sum(float(sample[key]) * weight for sample, weight in zip(samples, weights)) / total

    @staticmethod
    def _grade(up_probability: float, expected_return: float, max_return: float, mdd: float) -> str:
        if up_probability >= 80 and expected_return >= 3 and max_return >= 5 and mdd > -5:
            return "A+"
        if up_probability >= 70 and expected_return >= 2 and max_return >= 4:
            return "A"
        if up_probability >= 60 and expected_return > 0:
            return "B"
        if up_probability >= 50:
            return "C"
        return "D"
