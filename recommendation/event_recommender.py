from __future__ import annotations

import sqlite3
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from prediction.replay_prediction import ReplayPrediction, ReplayPredictionEngine
from similarity.replay_vector_index import ReplayVectorIndex
from similarity.sliding_replay_matcher import SlidingReplayWindowMatcher
from sto.structure_similarity import STOStructureSimilarityEngine
from weekly.shape_similarity import WeeklyShape, WeeklyShapeSimilarityEngine


@dataclass(frozen=True)
class ReplayMatch:
    event_id: str
    event_date: str
    market: str
    ticker: str
    name: str | None
    weekly_similarity: float
    sto_similarity: float
    final_similarity: float
    max_return: float | None
    max_drawdown: float | None
    equivalent_week_index: int
    future_start_week_index: int
    weeks_compared: int
    future_weeks_available: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


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
    replay_matches: list[ReplayMatch]
    prediction: ReplayPrediction | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["prediction"] = self.prediction.to_dict() if self.prediction is not None else None
        return data


class RecentMoneyEventRecommender:
    """ADE recommendation rule with vector prefilter, sliding Replay matching and prediction."""

    TIMELINE_CACHE_LIMIT = 512
    SHAPE_CACHE_LIMIT = 2048

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.price_repo = PriceRepository(self.db_path)
        self.weekly_shape_engine = WeeklyShapeSimilarityEngine(weeks=26)
        self.sto_structure_engine = STOStructureSimilarityEngine()
        self.sliding_matcher = SlidingReplayWindowMatcher(min_weeks=10, max_weeks=26)
        self.prediction_engine = ReplayPredictionEngine(self.db_path)
        self.vector_index = ReplayVectorIndex(self.db_path)
        self._timeline_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
        self._shape_cache: OrderedDict[tuple[str, int], WeeklyShape] = OrderedDict()

    def close(self) -> None:
        self._timeline_cache.clear()
        self._shape_cache.clear()
        self.vector_index.close()
        self.prediction_engine.close()
        self.price_repo.close()
        self.conn.close()

    def recommend(
        self,
        candidate_years: int = 2,
        lookback_months: int = 6,
        top_n: int = 20,
        weekly_pool_n: int = 100,
        min_weekly_similarity: float = 85.0,
        min_sto_similarity: float = 85.0,
        replay_top_n: int = 5,
    ) -> list[EventRecommendation]:
        candidates = self._recent_event_candidates(candidate_years)
        historical_events = self._historical_events()
        historical_by_id = {str(row["event_id"]): row for row in historical_events}
        recommendations: list[EventRecommendation] = []
        lookback_days = max(40, lookback_months * 22)
        replay_days = max(260, lookback_days + 132)

        for candidate in candidates:
            current_data = self.price_repo.fetch_dataframe(candidate["market"], candidate["ticker"], source="fdr")
            current_window = current_data.tail(lookback_days).reset_index(drop=True)
            if current_window.empty:
                continue
            current_weekly_shape = self.weekly_shape_engine.extract(current_window)
            current_sto_structure = self.sto_structure_engine.extract(current_data)

            candidate_events, vector_prefilter_used = self._vector_prefilter(
                candidate,
                historical_events,
                historical_by_id,
                weekly_pool_n=weekly_pool_n,
            )

            weekly_hits: list[tuple[float, sqlite3.Row, pd.DataFrame]] = []
            for event in candidate_events:
                if event["event_id"] == candidate["event_id"]:
                    continue
                replay_timeline = self._event_forward_window_days(event, days=replay_days)
                if replay_timeline.empty:
                    continue
                event_weekly_shape = self._cached_weekly_shape(event, replay_timeline, lookback_days)
                weekly_similarity = self.weekly_shape_engine.similarity(current_weekly_shape, event_weekly_shape)
                if weekly_similarity >= min_weekly_similarity:
                    weekly_hits.append((weekly_similarity, event, replay_timeline))

            weekly_hits = sorted(weekly_hits, key=lambda item: item[0], reverse=True)[:weekly_pool_n]
            replay_matches: list[ReplayMatch] = []
            for _prefilter_score, event, replay_timeline in weekly_hits:
                sliding = self.sliding_matcher.find_best(current_window, replay_timeline, future_min_weeks=4)
                if sliding is None:
                    continue
                if sliding.weekly_similarity < min_weekly_similarity or sliding.sto_similarity < min_sto_similarity:
                    continue
                replay_matches.append(
                    ReplayMatch(
                        event_id=str(event["event_id"]),
                        event_date=str(event["event_date"]),
                        market=str(event["market"]),
                        ticker=str(event["ticker"]),
                        name=event["name"],
                        weekly_similarity=sliding.weekly_similarity,
                        sto_similarity=sliding.sto_similarity,
                        final_similarity=sliding.final_similarity,
                        max_return=event["max_return"],
                        max_drawdown=event["max_drawdown"],
                        equivalent_week_index=sliding.end_week_index,
                        future_start_week_index=sliding.future_start_week_index,
                        weeks_compared=sliding.weeks_compared,
                        future_weeks_available=sliding.future_weeks_available,
                    )
                )

            replay_matches = sorted(replay_matches, key=lambda x: x.final_similarity, reverse=True)[:replay_top_n]
            if not replay_matches:
                continue

            best = replay_matches[0]
            prediction = self.prediction_engine.predict(replay_matches)
            reasons = [
                f"최근 {candidate_years}년 내 대금 이벤트 발생: {candidate['event_date']}",
                (
                    f"Replay Vector 1차 후보축소 적용: {len(candidate_events)}개 이벤트"
                    if vector_prefilter_used
                    else "Replay Vector 미사용: 전체 이벤트에서 기존 방식으로 검색"
                ),
                f"Replay DB에서 Top {len(replay_matches)} 유사 이벤트 검색",
                f"슬라이딩 매칭: Top1 Replay의 {best.equivalent_week_index}번째 주봉이 현재 NOW와 가장 유사",
                f"비교 구간 {best.weeks_compared}주, 이후 확인 가능 구간 {best.future_weeks_available}주",
                f"Top1 주봉 차트형태 유사도 {best.weekly_similarity:.2f}%",
                f"Top1 STO 3계층 구조 유사도 {best.sto_similarity:.2f}%",
                f"현재 STO 구조: {current_sto_structure.arrangement}",
                f"Top1 매칭 이벤트 이후 최대수익 {best.max_return}%, 최대낙폭 {best.max_drawdown}%",
            ]
            if prediction is not None:
                reasons.extend(
                    [
                        f"7거래일 이내 상승확률 {prediction.seven_day_up_probability:.2f}%",
                        f"7거래일 기대수익 {prediction.seven_day_expected_return:+.2f}%",
                        f"7거래일 예상 최대수익 {prediction.expected_max_return_7d:+.2f}%",
                        f"예상 최고점 도달 {prediction.expected_peak_day:.1f}일, 권장 보유기간 {prediction.holding_days}일",
                        f"목표수익 {prediction.target_return:+.2f}%, 참고 손절폭 {prediction.stop_return:.2f}%",
                        f"Replay Prediction 등급 {prediction.grade}",
                    ]
                )
            recommendations.append(
                EventRecommendation(
                    market=str(candidate["market"]),
                    ticker=str(candidate["ticker"]),
                    name=candidate["name"],
                    recent_event_date=str(candidate["event_date"]),
                    recent_money_ratio=float(candidate["money_ratio_120d"]),
                    matched_event_id=best.event_id,
                    matched_event_date=best.event_date,
                    weekly_similarity=best.weekly_similarity,
                    sto_similarity=best.sto_similarity,
                    final_similarity=best.final_similarity,
                    matched_max_return=best.max_return,
                    matched_max_drawdown=best.max_drawdown,
                    decision=self._decision(best.final_similarity, best.max_return, best.max_drawdown, prediction),
                    reasons=reasons,
                    replay_matches=replay_matches,
                    prediction=prediction,
                )
            )

        return sorted(recommendations, key=self._sort_key, reverse=True)[:top_n]

    def _vector_prefilter(
        self,
        candidate: sqlite3.Row,
        historical_events: list[sqlite3.Row],
        historical_by_id: dict[str, sqlite3.Row],
        weekly_pool_n: int,
    ) -> tuple[list[sqlite3.Row], bool]:
        if self.vector_index.count() <= 0:
            return historical_events, False

        ranked = self.vector_index.rank_similar(
            query_event_id=str(candidate["event_id"]),
            candidate_event_ids=list(historical_by_id),
            limit=max(120, int(weekly_pool_n) * 2),
        )
        selected = [historical_by_id[event_id] for event_id, _score in ranked if event_id in historical_by_id]
        return (selected, True) if selected else (historical_events, False)

    def _cached_weekly_shape(
        self,
        event: sqlite3.Row,
        replay_timeline: pd.DataFrame,
        lookback_days: int,
    ) -> WeeklyShape:
        key = (str(event["event_id"]), int(lookback_days))
        cached = self._shape_cache.get(key)
        if cached is not None:
            self._shape_cache.move_to_end(key)
            return cached
        first_segment = replay_timeline.head(lookback_days).reset_index(drop=True)
        shape = self.weekly_shape_engine.extract(first_segment)
        self._shape_cache[key] = shape
        self._shape_cache.move_to_end(key)
        while len(self._shape_cache) > self.SHAPE_CACHE_LIMIT:
            self._shape_cache.popitem(last=False)
        return shape

    @staticmethod
    def _sort_key(item: EventRecommendation) -> tuple[float, float, float]:
        prediction = item.prediction
        seven_day_probability = prediction.seven_day_up_probability if prediction is not None else -1.0
        seven_day_return = prediction.seven_day_expected_return if prediction is not None else -999.0
        return seven_day_probability, seven_day_return, item.final_similarity

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

    def _event_forward_window_days(self, event: sqlite3.Row, days: int) -> pd.DataFrame:
        event_id = str(event["event_id"])
        cached = self._timeline_cache.get(event_id)
        if cached is not None:
            self._timeline_cache.move_to_end(event_id)
            return cached.head(days).copy()

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
        end = min(len(df), start + max(260, days))
        timeline = df.iloc[start:end].reset_index(drop=True)
        self._timeline_cache[event_id] = timeline
        self._timeline_cache.move_to_end(event_id)
        while len(self._timeline_cache) > self.TIMELINE_CACHE_LIMIT:
            self._timeline_cache.popitem(last=False)
        return timeline.head(days).copy()

    def _event_forward_window(self, event: sqlite3.Row, months: int) -> pd.DataFrame:
        return self._event_forward_window_days(event, days=max(40, months * 22))

    @staticmethod
    def _decision(
        similarity: float,
        max_return: float | None,
        max_drawdown: float | None,
        prediction: ReplayPrediction | None,
    ) -> str:
        if prediction is not None:
            if prediction.seven_day_up_probability >= 70 and prediction.seven_day_expected_return > 0 and prediction.grade in {"A+", "A", "B"}:
                return "RECOMMEND"
            if prediction.seven_day_up_probability >= 55 and prediction.seven_day_expected_return > 0:
                return "WATCH"
        if similarity >= 85 and (max_return or 0) > 20 and (max_drawdown is None or max_drawdown > -25):
            return "RECOMMEND"
        if similarity >= 75 and (max_return or 0) > 10:
            return "WATCH"
        return "WAIT"
