from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from similarity.replay_candidate import ReplayCandidate
from similarity.sto_similarity import STOSimilarityEngine
from similarity.weekly_similarity import WeeklySimilarityEngine
from sto.layer_engine import STO3LayerEngine, STOLayers
from weekly.pattern import WeeklyPattern, WeeklyPatternEngine


class ADESimilarityEngine:
    """ADE similarity is not weighted average.

    It is an AND process:
    1) find most similar weekly chart structures,
    2) inside that group find most similar STO 3-layer structures,
    3) only the survivors become Replay candidates.
    """

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.price_repo = PriceRepository(self.db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.weekly_engine = WeeklyPatternEngine()
        self.sto_engine = STO3LayerEngine()
        self.weekly_similarity = WeeklySimilarityEngine()
        self.sto_similarity = STOSimilarityEngine()

    def close(self) -> None:
        self.price_repo.close()
        self.conn.close()

    def search(
        self,
        market: str,
        ticker: str,
        weekly_top_n: int = 100,
        sto_top_n: int = 20,
    ) -> list[ReplayCandidate]:
        query_data = self.price_repo.fetch_dataframe(market, ticker, source="fdr")
        query_weekly = self.weekly_engine.extract(query_data)
        query_sto = self.sto_engine.extract(query_data)

        rows = self.conn.execute("SELECT event_id, market, ticker, event_date FROM replay_events").fetchall()
        weekly_targets: list[tuple[str, WeeklyPattern]] = []
        target_data_cache: dict[str, pd.DataFrame] = {}
        for row in rows:
            event_id = str(row["event_id"])
            data = self.price_repo.fetch_dataframe(row["market"], row["ticker"], source="fdr")
            window = self._window_until_event(data, str(row["event_date"]))
            if window.empty:
                continue
            target_data_cache[event_id] = window
            weekly_targets.append((event_id, self.weekly_engine.extract(window)))

        weekly_hits = self.weekly_similarity.filter(query_weekly, weekly_targets, top_n=weekly_top_n)
        weekly_map = {item.event_id: item for item in weekly_hits}

        sto_targets: list[tuple[str, STOLayers]] = []
        for hit in weekly_hits:
            window = target_data_cache.get(hit.event_id)
            if window is None or window.empty:
                continue
            sto_targets.append((hit.event_id, self.sto_engine.extract(window)))

        sto_hits = self.sto_similarity.filter(query_sto, sto_targets, top_n=sto_top_n)
        candidates: list[ReplayCandidate] = []
        for hit in sto_hits:
            weekly = weekly_map[hit.event_id]
            final_similarity = min(weekly.weekly_similarity, hit.sto_similarity)
            candidates.append(
                ReplayCandidate(
                    event_id=hit.event_id,
                    weekly_similarity=weekly.weekly_similarity,
                    sto_similarity=hit.sto_similarity,
                    final_similarity=round(final_similarity, 2),
                    weekly_pattern=weekly.weekly_pattern,
                    sto_structure=hit.sto_structure,
                )
            )
        return sorted(candidates, key=lambda item: item.final_similarity, reverse=True)

    @staticmethod
    def _window_until_event(data: pd.DataFrame, event_date: str, lookback_days: int = 520) -> pd.DataFrame:
        df = data.copy()
        if "Date" not in df.columns:
            return pd.DataFrame()
        df["Date"] = pd.to_datetime(df["Date"])
        dates = df["Date"].dt.date.astype(str)
        matches = dates[dates == event_date]
        if matches.empty:
            return pd.DataFrame()
        event_index = int(matches.index[0])
        return df.iloc[max(0, event_index - lookback_days) : event_index + 1].reset_index(drop=True)
