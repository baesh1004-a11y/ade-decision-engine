from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from recommendation.event_recommender import EventRecommendation, ReplayMatch
from sto.structure_similarity import STOStructure, STOStructureSimilarityEngine
from surge.pattern_engine import PATTERN_VERSION, SurgeBuildStats, SurgePatternRepository
from weekly.shape_similarity import WeeklyShape, WeeklyShapeSimilarityEngine


MULTI_PATTERN_VERSION = "pre-surge-120d-multi-horizon-v3-sto-trajectory"

SURGE_CLASSES = (
    ("FAST", 5, 1.00),
    ("QUICK", 10, 0.90),
    ("SWING", 15, 0.80),
    ("POSITION", 20, 0.70),
)


class MultiHorizonSurgePatternBuilder:
    """Build pre-surge patterns classified by the first 30% target horizon.

    Classification is exclusive:
    FAST      : target first reached in sessions 1-5
    QUICK     : target first reached in sessions 6-10
    SWING     : target first reached in sessions 11-15
    POSITION  : target first reached in sessions 16-20
    """

    def __init__(
        self,
        db_path: str | Path,
        price_source: str,
        source_money_ratio: float = 10.0,
        observation_days: int = 500,
        surge_return: float = 30.0,
        pattern_days: int = 120,
        cooldown_days: int = 20,
    ) -> None:
        self.db_path = Path(db_path)
        self.price_source = price_source
        self.source_money_ratio = float(source_money_ratio)
        self.observation_days = int(observation_days)
        self.surge_return = float(surge_return)
        self.pattern_days = int(pattern_days)
        self.cooldown_days = int(cooldown_days)
        self.price_repo = PriceRepository(self.db_path)
        self.repo = SurgePatternRepository(self.db_path)
        self.weekly_engine = WeeklyShapeSimilarityEngine(weeks=26)
        self.sto_engine = STOStructureSimilarityEngine()
        self._migrate_schema()

    def close(self) -> None:
        self.price_repo.close()
        self.repo.close()

    def _migrate_schema(self) -> None:
        columns = {
            str(row[1])
            for row in self.repo.conn.execute("PRAGMA table_info(surge_patterns)").fetchall()
        }
        additions = {
            "surge_class": "TEXT NOT NULL DEFAULT 'FAST'",
            "surge_horizon_days": "INTEGER NOT NULL DEFAULT 5",
            "target_hit_day": "INTEGER NOT NULL DEFAULT 5",
            "surge_return_pct": "REAL NOT NULL DEFAULT 0",
            "return_5d": "REAL NOT NULL DEFAULT 0",
            "return_10d": "REAL NOT NULL DEFAULT 0",
            "return_15d": "REAL NOT NULL DEFAULT 0",
            "return_20d": "REAL NOT NULL DEFAULT 0",
            "speed_weight": "REAL NOT NULL DEFAULT 1.0",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.repo.conn.execute(
                    f"ALTER TABLE surge_patterns ADD COLUMN {name} {definition}"
                )
        self.repo.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_surge_pattern_class "
            "ON surge_patterns(market, surge_class, surge_return_pct DESC)"
        )
        self.repo.conn.commit()

    def build(self, market: str, clear: bool = False, limit: int = 0) -> SurgeBuildStats:
        if clear:
            self.repo.clear(market)
        events = self.repo.conn.execute(
            """
            SELECT event_id, market, ticker, name, event_date, money_ratio_120d
            FROM replay_events
            WHERE market=? AND money_ratio_120d>=?
            ORDER BY event_date, ticker
            """,
            (market, self.source_money_ratio),
        ).fetchall()
        if limit > 0:
            events = events[:limit]

        patterns = 0
        pattern_bars = 0
        for index, event in enumerate(events, start=1):
            data = self.price_repo.fetch_dataframe(
                market, str(event["ticker"]), source=self.price_source
            )
            df = self._prepare(data)
            event_index = self._date_index(df, str(event["event_date"]))
            if event_index is None:
                continue
            hits = self._find_surges(df, event_index)
            for hit in hits:
                pattern_end = int(hit["start_index"]) - 1
                pattern_start = pattern_end - self.pattern_days + 1
                if pattern_start < 0:
                    continue
                window = df.iloc[pattern_start : pattern_end + 1].reset_index(drop=True)
                if len(window) != self.pattern_days:
                    continue
                weekly = self.weekly_engine.extract(window)
                sto = self.sto_engine.extract(window)
                pattern_id = (
                    f"{market.upper()}:{event['ticker']}:{event['event_date']}:"
                    f"SURGE:{hit['start_date']}:{hit['surge_class']}"
                )
                values = {
                    "pattern_id": pattern_id,
                    "source_event_id": str(event["event_id"]),
                    "market": market,
                    "ticker": str(event["ticker"]),
                    "name": event["name"],
                    "money_event_date": str(event["event_date"]),
                    "money_ratio_120d": float(event["money_ratio_120d"]),
                    "pattern_start_date": str(pd.Timestamp(window.iloc[0]["Date"]).date()),
                    "pattern_end_date": str(pd.Timestamp(window.iloc[-1]["Date"]).date()),
                    "surge_start_date": str(hit["start_date"]),
                    "surge_peak_date": str(hit["peak_date"]),
                    "surge_return_5d": float(hit["surge_return_pct"]),
                    "observation_days": int(hit["start_index"]) - event_index,
                    "weekly_shape_json": json.dumps(weekly.to_dict(), ensure_ascii=False),
                    "sto_json": json.dumps(sto.to_dict(), ensure_ascii=False),
                }
                self.repo.upsert_pattern(values, window)
                self.repo.conn.execute(
                    """
                    UPDATE surge_patterns
                    SET pattern_version=?, surge_class=?, surge_horizon_days=?,
                        target_hit_day=?, surge_return_pct=?, return_5d=?, return_10d=?,
                        return_15d=?, return_20d=?, speed_weight=?, updated_at=CURRENT_TIMESTAMP
                    WHERE pattern_id=?
                    """,
                    (
                        MULTI_PATTERN_VERSION,
                        hit["surge_class"],
                        hit["surge_horizon_days"],
                        hit["target_hit_day"],
                        hit["surge_return_pct"],
                        hit["return_5d"],
                        hit["return_10d"],
                        hit["return_15d"],
                        hit["return_20d"],
                        hit["speed_weight"],
                        pattern_id,
                    ),
                )
                patterns += 1
                pattern_bars += len(window)
            self.repo.conn.commit()
            class_counts: dict[str, int] = {}
            for hit in hits:
                key = str(hit["surge_class"])
                class_counts[key] = class_counts.get(key, 0) + 1
            print(
                f"[{index}/{len(events)}] {market.upper()}:{event['ticker']} "
                f"money={event['event_date']} surges={len(hits)} classes={class_counts}"
            )
        return SurgeBuildStats(len(events), patterns, pattern_bars)

    def _find_surges(self, df: pd.DataFrame, event_index: int) -> list[dict[str, object]]:
        max_horizon = 20
        start = max(event_index + 1, self.pattern_days)
        end = min(len(df) - max_horizon, event_index + self.observation_days)
        hits: list[dict[str, object]] = []
        last_hit = -10_000
        for i in range(start, max(start, end)):
            if i - last_hit < self.cooldown_days:
                continue
            entry = float(df.iloc[i - 1]["Close"])
            if entry <= 0:
                continue
            future = df.iloc[i : i + max_horizon].reset_index(drop=True)
            if len(future) < max_horizon:
                continue
            high_returns = (future["High"].astype(float) / entry - 1.0) * 100.0
            hit_positions = high_returns.index[high_returns >= self.surge_return].tolist()
            if not hit_positions:
                continue
            first_hit_offset = int(hit_positions[0])
            target_hit_day = first_hit_offset + 1
            surge_class, horizon, speed_weight = self._class_for_day(target_hit_day)
            horizon_slice = future.iloc[:horizon]
            peak_offset = int(horizon_slice["High"].astype(float).values.argmax())
            peak = float(horizon_slice.iloc[peak_offset]["High"])
            surge_return_pct = (peak / entry - 1.0) * 100.0

            def horizon_return(days: int) -> float:
                peak_value = float(future.iloc[:days]["High"].astype(float).max())
                return round((peak_value / entry - 1.0) * 100.0, 2)

            hits.append(
                {
                    "start_index": i,
                    "start_date": str(pd.Timestamp(df.iloc[i]["Date"]).date()),
                    "peak_date": str(pd.Timestamp(horizon_slice.iloc[peak_offset]["Date"]).date()),
                    "surge_class": surge_class,
                    "surge_horizon_days": horizon,
                    "target_hit_day": target_hit_day,
                    "surge_return_pct": round(surge_return_pct, 2),
                    "return_5d": horizon_return(5),
                    "return_10d": horizon_return(10),
                    "return_15d": horizon_return(15),
                    "return_20d": horizon_return(20),
                    "speed_weight": speed_weight,
                }
            )
            last_hit = i
        return hits

    @staticmethod
    def _class_for_day(day: int) -> tuple[str, int, float]:
        for name, horizon, weight in SURGE_CLASSES:
            if day <= horizon:
                return name, horizon, weight
        return "POSITION", 20, 0.70

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" not in df.columns:
            return pd.DataFrame()
        df["Date"] = pd.to_datetime(df["Date"])
        for column in ["Open", "High", "Low", "Close", "Volume"]:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        return df.dropna(
            subset=["Date", "Open", "High", "Low", "Close", "Volume"]
        ).sort_values("Date").reset_index(drop=True)

    @staticmethod
    def _date_index(df: pd.DataFrame, date_text: str) -> int | None:
        if df.empty:
            return None
        matches = df.index[df["Date"].dt.date.astype(str) == date_text].tolist()
        return int(matches[0]) if matches else None


class MultiHorizonSurgePatternRecommender:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.price_repo = PriceRepository(self.db_path)
        self.weekly_engine = WeeklyShapeSimilarityEngine(weeks=26)
        self.sto_engine = STOStructureSimilarityEngine()

    def close(self) -> None:
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
        market, source = self._market_and_source()
        patterns = self.conn.execute(
            """
            SELECT * FROM surge_patterns
            WHERE market=? AND pattern_version=?
            ORDER BY speed_weight DESC, surge_return_pct DESC, surge_start_date DESC
            LIMIT ?
            """,
            (market, MULTI_PATTERN_VERSION, max(500, weekly_pool_n * 20)),
        ).fetchall()
        if not patterns:
            raise RuntimeError(
                "STO 궤적 비교용 급등직전 패턴 DB가 없습니다. run_build_surge_patterns.py --full을 다시 실행하세요."
            )
        prepared = [self._prepare_pattern(row) for row in patterns]
        prepared = [item for item in prepared if item is not None]
        ranked_results: list[tuple[float, EventRecommendation]] = []

        for symbol in self._active_symbols(market):
            data = self.price_repo.fetch_dataframe(market, str(symbol["ticker"]), source=source)
            current = data.tail(120).reset_index(drop=True)
            if len(current) < 120:
                continue
            current_weekly = self.weekly_engine.extract(current)
            current_sto = self.sto_engine.extract(current)
            candidate_matches: list[tuple[float, sqlite3.Row, ReplayMatch]] = []
            for row, weekly, sto in prepared:
                chart_score = self.weekly_engine.similarity(current_weekly, weekly)
                if chart_score < min_weekly_similarity:
                    continue
                sto_score = self.sto_engine.similarity(current_sto, sto)
                if sto_score < min_sto_similarity:
                    continue
                raw_similarity = min(chart_score, sto_score)
                weighted_score = raw_similarity * float(row["speed_weight"] or 1.0)
                match = ReplayMatch(
                    event_id=str(row["pattern_id"]),
                    event_date=str(row["surge_start_date"]),
                    market=str(row["market"]),
                    ticker=str(row["ticker"]),
                    name=row["name"],
                    weekly_similarity=chart_score,
                    sto_similarity=sto_score,
                    final_similarity=weighted_score,
                    max_return=float(row["surge_return_pct"]),
                    max_drawdown=None,
                    equivalent_week_index=25,
                    future_start_week_index=26,
                    weeks_compared=26,
                    future_weeks_available=max(1, int(row["surge_horizon_days"]) // 5),
                )
                candidate_matches.append((weighted_score, row, match))

            candidate_matches.sort(
                key=lambda item: (
                    item[0],
                    item[2].weekly_similarity,
                    item[2].sto_similarity,
                    item[2].max_return or 0.0,
                ),
                reverse=True,
            )
            selected = candidate_matches[:replay_top_n]
            if not selected:
                continue

            matches = [item[2] for item in selected]
            best_weighted, best_row, best = selected[0]
            average_surge = sum(float(item.max_return or 0.0) for item in matches) / len(matches)
            class_counts: dict[str, int] = {}
            weighted_days = 0.0
            total_weight = 0.0
            for _, row, _ in selected:
                cls = str(row["surge_class"])
                class_counts[cls] = class_counts.get(cls, 0) + 1
                weight = float(row["speed_weight"] or 1.0)
                weighted_days += float(row["target_hit_day"] or row["surge_horizon_days"]) * weight
                total_weight += weight
            expected_days = weighted_days / total_weight if total_weight else 0.0
            distribution = " · ".join(
                f"{name} {class_counts.get(name, 0)}" for name, _, _ in SURGE_CLASSES
            )
            reasons = [
                "현재 최근 120거래일을 과거 다중기간 급등직전 120일 패턴과 비교",
                f"차트 유사도 {best.weekly_similarity:.2f}% · STO 3계층 궤적 유사도 {best.sto_similarity:.2f}%",
                f"Top1 유형 {best_row['surge_class']} · 30% 최초 도달 {int(best_row['target_hit_day'])}거래일",
                f"속도 가중점수 {best_weighted:.2f} · 예상 30% 도달 {expected_days:.1f}거래일",
                f"매칭 {len(matches)}건 · 유형분포 {distribution}",
                f"매칭 사례 평균 최대상승률 {average_surge:+.2f}%",
            ]
            recommendation = EventRecommendation(
                market=market,
                ticker=str(symbol["ticker"]),
                name=symbol["name"],
                recent_event_date=str(pd.Timestamp(current.iloc[-1]["Date"]).date()),
                recent_money_ratio=0.0,
                matched_event_id=best.event_id,
                matched_event_date=best.event_date,
                weekly_similarity=best.weekly_similarity,
                sto_similarity=best.sto_similarity,
                final_similarity=best.final_similarity,
                matched_max_return=best.max_return,
                matched_max_drawdown=None,
                decision="RECOMMEND" if len(matches) >= 2 else "WATCH",
                reasons=reasons,
                replay_matches=matches,
                prediction=None,
            )
            confidence = min(1.0, len(matches) / max(2.0, float(replay_top_n)))
            ranking_score = best_weighted * (0.85 + 0.15 * confidence)
            ranked_results.append((ranking_score, recommendation))

        ranked_results.sort(
            key=lambda item: (
                item[0],
                item[1].final_similarity,
                len(item[1].replay_matches),
                item[1].matched_max_return or 0.0,
            ),
            reverse=True,
        )
        return [item[1] for item in ranked_results[:top_n]]

    def _market_and_source(self) -> tuple[str, str]:
        row = self.conn.execute(
            "SELECT market, source FROM price_bars GROUP BY market, source ORDER BY COUNT(*) DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("가격 데이터가 없습니다.")
        return str(row["market"]), str(row["source"])

    def _active_symbols(self, market: str) -> list[dict[str, str | None]]:
        if market == "us" and self._table_exists("us_universe"):
            rows = self.conn.execute(
                "SELECT symbol AS ticker, name FROM us_universe WHERE enabled=1 ORDER BY market_cap DESC"
            ).fetchall()
            return [dict(row) for row in rows]
        rows = self.conn.execute(
            "SELECT DISTINCT ticker, ticker AS name FROM price_bars WHERE market=? ORDER BY ticker",
            (market,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _table_exists(self, name: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None

    @staticmethod
    def _prepare_pattern(row: sqlite3.Row) -> tuple[sqlite3.Row, WeeklyShape, STOStructure] | None:
        try:
            weekly = WeeklyShape(**json.loads(str(row["weekly_shape_json"])))
            sto = STOStructure(**json.loads(str(row["sto_json"])))
            return row, weekly, sto
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
