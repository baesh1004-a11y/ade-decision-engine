from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from sto.structure_similarity import STOStructureSimilarityEngine
from weekly.shape_similarity import WeeklyShapeSimilarityEngine


@dataclass(frozen=True)
class EventRecommendation:
    market: str
    ticker: str
    name: str | None
    recent_event_date: str
    recent_money_ratio: float
    matched_event_id: str
    matched_event_date: str
    weekly_similarity: float
    sto_similarity: float
    final_similarity: float
    matched_max_return: float | None
    matched_max_drawdown: float | None
    decision: str
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class RecentMoneyEventRecommender:
    """ADE v3 recommendation rule.

    Candidate = recent money event stock.
    Match = 6-month weekly chart shape AND current STO 3-layer structure.
    """

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.price_repo = PriceRepository(self.db_path)
        self.weekly_shape_engine = WeeklyShapeSimilarityEngine(weeks=26)
        self.sto_structure_engine = STOStructureSimilarityEngine()

    def close(self) -> None:
        self.price_repo.close()
        self.conn.close()

    def recommend(
        self,
        candidate_years: int = 2,
        lookback_months: int = 6,
        top_n: int = 20,
        weekly_pool_n: int = 100,
        min_weekly_similarity: float = 70.0,
        min_sto_similarity: float = 70.0,
    ) -> list[EventRecommendation]:
        candidates = self._recent_event_candidates(candidate_years)
        historical_events = self._historical_events()
        recommendations: list[EventRecommendation] = []

        for candidate in candidates:
            current_data = self.price_repo.fetch_dataframe(candidate["market"], candidate["ticker"], source="fdr")
            current_window = current_data.tail(max(40, lookback_months * 22)).reset_index(drop=True)
            if current_window.empty:
                continue
            current_weekly_shape = self.weekly_shape_engine.extract(current_window)
            current_sto_structure = self.sto_structure_engine.extract(current_data)

            weekly_hits: list[tuple[float, sqlite3.Row, pd.DataFrame]] = []
            for event in historical_events:
                if event["event_id"] == candidate["event_id"]:
                    continue
                event_window = self._event_forward_window(event, lookback_months)
                if event_window.empty:
                    continue
                event_weekly_shape = self.weekly_shape_engine.extract(event_window)
                weekly_similarity = self.weekly_shape_engine.similarity(current_weekly_shape, event_weekly_shape)
                if weekly_similarity >= min_weekly_similarity:
                    weekly_hits.append((weekly_similarity, event, event_window))

            weekly_hits = sorted(weekly_hits, key=lambda item: item[0], reverse=True)[:weekly_pool_n]
            best: EventRecommendation | None = None
            for weekly_similarity, event, event_window in weekly_hits:
                event_sto_structure = self.sto_structure_engine.extract(event_window)
                sto_similarity = self.sto_structure_engine.similarity(current_sto_structure, event_sto_structure)
                if sto_similarity < min_sto_similarity:
                    continue
                final_similarity = min(weekly_similarity, sto_similarity)
                rec = EventRecommendation(
                    market=str(candidate["market"]),
                    ticker=str(candidate["ticker"]),
                    name=candidate["name"],
                    recent_event_date=str(candidate["event_date"]),
                    recent_money_ratio=float(candidate["money_ratio_120d"]),
                    matched_event_id=str(event["event_id"]),
                    matched_event_date=str(event["event_date"]),
                    weekly_similarity=round(weekly_similarity, 2),
                    sto_similarity=round(sto_similarity, 2),
                    final_similarity=round(final_similarity, 2),
                    matched_max_return=event["max_return"],
                    matched_max_drawdown=event["max_drawdown"],
                    decision=self._decision(final_similarity, event["max_return"], event["max_drawdown"]),
                    reasons=[
                        f"최근 {candidate_years}년 내 대금 이벤트 발생: {candidate['event_date']}",
                        f"최근 {lookback_months}개월 주봉 차트형태 유사도 {weekly_similarity:.2f}%",
                        f"현재 STO 3계층 구조 유사도 {sto_similarity:.2f}%",
                        f"현재 STO 구조: {current_sto_structure.arrangement}",
                        f"과거 매칭 이벤트 이후 최대수익 {event['max_return']}%, 최대낙폭 {event['max_drawdown']}%",
                    ],
                )
                if best is None or rec.final_similarity > best.final_similarity:
                    best = rec
            if best is not None:
                recommendations.append(best)

        return sorted(recommendations, key=lambda item: (item.final_similarity, item.matched_max_return or -999), reverse=True)[:top_n]

    def _recent_event_candidates(self, years: int) -> list[sqlite3.Row]:
        cutoff = (date.today() - timedelta(days=365 * years)).isoformat()
        rows = self.conn.execute(
            """
            SELECT * FROM replay_events
            WHERE event_date >= ?
            ORDER BY event_date DESC, money_ratio_120d DESC
            """,
            (cutoff,),
        ).fetchall()
        seen: set[str] = set()
        result: list[sqlite3.Row] = []
        for row in rows:
            key = f"{row['market']}:{row['ticker']}"
            if key in seen:
                continue
            seen.add(key)
            result.append(row)
        return result

    def _historical_events(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM replay_events ORDER BY event_date").fetchall()

    def _event_forward_window(self, event: sqlite3.Row, months: int) -> pd.DataFrame:
        data = self.price_repo.fetch_dataframe(event["market"], event["ticker"], source="fdr")
        if data.empty or "Date" not in data.columns:
            return pd.DataFrame()
        df = data.copy()
        df["Date"] = pd.to_datetime(df["Date"])
        dates = df["Date"].dt.date.astype(str)
        matches = dates[dates == event["event_date"]]
        if matches.empty:
            return pd.DataFrame()
        start = int(matches.index[0])
        end = min(len(df), start + max(40, months * 22))
        return df.iloc[start:end].reset_index(drop=True)

    @staticmethod
    def _decision(similarity: float, max_return: float | None, max_drawdown: float | None) -> str:
        if similarity >= 85 and (max_return or 0) > 20 and (max_drawdown is None or max_drawdown > -25):
            return "RECOMMEND"
        if similarity >= 75 and (max_return or 0) > 10:
            return "WATCH"
        return "WAIT"
