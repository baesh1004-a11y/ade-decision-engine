from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from sto.structure_similarity import STOStructureSimilarityEngine
from weekly.shape_similarity import WeeklyShapeSimilarityEngine


@dataclass(frozen=True)
class SlidingReplayMatch:
    start_week_index: int
    end_week_index: int
    future_start_week_index: int
    weekly_similarity: float
    sto_similarity: float
    final_similarity: float
    weeks_compared: int
    future_weeks_available: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SlidingReplayWindowMatcher:
    """Find where the current chart best fits inside a replay timeline.

    Current chart ends at NOW. The matcher slides the same-length weekly window
    across a replay timeline and finds the window whose end point is most similar
    to current NOW. The future path begins immediately after that end point.
    """

    def __init__(self, min_weeks: int = 10, max_weeks: int = 26) -> None:
        self.min_weeks = min_weeks
        self.max_weeks = max_weeks
        self.weekly_engine = WeeklyShapeSimilarityEngine(weeks=max_weeks)
        self.sto_engine = STOStructureSimilarityEngine()

    def find_best(
        self,
        current_daily: pd.DataFrame,
        replay_daily: pd.DataFrame,
        future_min_weeks: int = 4,
    ) -> SlidingReplayMatch | None:
        current_weekly = self._to_weekly(current_daily).tail(self.max_weeks).reset_index(drop=True)
        replay_weekly = self._to_weekly(replay_daily).reset_index(drop=True)
        if len(current_weekly) < self.min_weeks or len(replay_weekly) < self.min_weeks:
            return None

        window_weeks = min(len(current_weekly), self.max_weeks)
        query_weekly = current_weekly.tail(window_weeks).reset_index(drop=True)
        query_shape = self.weekly_engine.extract(query_weekly)
        query_sto = self.sto_engine.extract(current_daily)

        max_start = len(replay_weekly) - window_weeks
        if max_start < 0:
            return None

        best: SlidingReplayMatch | None = None
        for start in range(0, max_start + 1):
            end = start + window_weeks - 1
            future_weeks = len(replay_weekly) - end - 1
            if future_weeks < future_min_weeks:
                continue
            candidate_weekly = replay_weekly.iloc[start : end + 1].reset_index(drop=True)
            candidate_shape = self.weekly_engine.extract(candidate_weekly)
            weekly_similarity = self.weekly_engine.similarity(query_shape, candidate_shape)
            candidate_daily = self._weekly_date_slice(replay_daily, candidate_weekly)
            candidate_sto = self.sto_engine.extract(candidate_daily if not candidate_daily.empty else candidate_weekly)
            sto_similarity = self.sto_engine.similarity(query_sto, candidate_sto)
            final_similarity = min(weekly_similarity, sto_similarity)
            match = SlidingReplayMatch(
                start_week_index=start,
                end_week_index=end,
                future_start_week_index=end + 1,
                weekly_similarity=round(weekly_similarity, 2),
                sto_similarity=round(sto_similarity, 2),
                final_similarity=round(final_similarity, 2),
                weeks_compared=window_weeks,
                future_weeks_available=future_weeks,
            )
            if best is None or match.final_similarity > best.final_similarity:
                best = match
        return best

    @staticmethod
    def _to_weekly(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" not in df.columns:
            df = df.reset_index().rename(columns={"index": "Date"})
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).sort_values("Date")
        return df.set_index("Date").resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna().reset_index()

    @staticmethod
    def _weekly_date_slice(daily: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
        if daily.empty or weekly.empty or "Date" not in daily.columns or "Date" not in weekly.columns:
            return pd.DataFrame()
        df = daily.copy()
        df["Date"] = pd.to_datetime(df["Date"])
        start = pd.to_datetime(weekly["Date"].iloc[0]) - pd.Timedelta(days=6)
        end = pd.to_datetime(weekly["Date"].iloc[-1])
        return df[(df["Date"] >= start) & (df["Date"] <= end)].reset_index(drop=True)
