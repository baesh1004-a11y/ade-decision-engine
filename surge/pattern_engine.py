from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from recommendation.event_recommender import EventRecommendation, ReplayMatch
from sto.structure_similarity import STOStructure, STOStructureSimilarityEngine
from weekly.shape_similarity import WeeklyShape, WeeklyShapeSimilarityEngine


PATTERN_VERSION = "pre-surge-120d-v1"


@dataclass(frozen=True)
class SurgeBuildStats:
    source_events: int
    patterns: int
    pattern_bars: int


class SurgePatternRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS surge_patterns (
                pattern_id TEXT PRIMARY KEY,
                pattern_version TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                money_event_date TEXT NOT NULL,
                money_ratio_120d REAL NOT NULL,
                pattern_start_date TEXT NOT NULL,
                pattern_end_date TEXT NOT NULL,
                surge_start_date TEXT NOT NULL,
                surge_peak_date TEXT NOT NULL,
                surge_return_5d REAL NOT NULL,
                observation_days INTEGER NOT NULL,
                weekly_shape_json TEXT NOT NULL,
                sto_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS surge_pattern_bars (
                pattern_id TEXT NOT NULL,
                day_index INTEGER NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                normalized_close REAL NOT NULL,
                PRIMARY KEY(pattern_id, day_index)
            );
            CREATE INDEX IF NOT EXISTS idx_surge_pattern_market
                ON surge_patterns(market, surge_return_5d DESC, surge_start_date);
            CREATE INDEX IF NOT EXISTS idx_surge_pattern_symbol
                ON surge_patterns(market, ticker, surge_start_date);
            """
        )
        self.conn.commit()

    def clear(self, market: str | None = None) -> None:
        if market is None:
            self.conn.execute("DELETE FROM surge_pattern_bars")
            self.conn.execute("DELETE FROM surge_patterns")
        else:
            ids = [
                row["pattern_id"]
                for row in self.conn.execute(
                    "SELECT pattern_id FROM surge_patterns WHERE market=?", (market,)
                ).fetchall()
            ]
            self.conn.executemany(
                "DELETE FROM surge_pattern_bars WHERE pattern_id=?",
                [(pattern_id,) for pattern_id in ids],
            )
            self.conn.execute("DELETE FROM surge_patterns WHERE market=?", (market,))
        self.conn.commit()

    def upsert_pattern(self, values: dict[str, object], bars: pd.DataFrame) -> None:
        self.conn.execute(
            """
            INSERT INTO surge_patterns(
                pattern_id, pattern_version, source_event_id, market, ticker, name,
                money_event_date, money_ratio_120d, pattern_start_date,
                pattern_end_date, surge_start_date, surge_peak_date,
                surge_return_5d, observation_days, weekly_shape_json, sto_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(pattern_id) DO UPDATE SET
                name=excluded.name,
                money_ratio_120d=excluded.money_ratio_120d,
                pattern_start_date=excluded.pattern_start_date,
                pattern_end_date=excluded.pattern_end_date,
                surge_peak_date=excluded.surge_peak_date,
                surge_return_5d=excluded.surge_return_5d,
                observation_days=excluded.observation_days,
                weekly_shape_json=excluded.weekly_shape_json,
                sto_json=excluded.sto_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                values["pattern_id"], PATTERN_VERSION, values["source_event_id"],
                values["market"], values["ticker"], values.get("name"),
                values["money_event_date"], values["money_ratio_120d"],
                values["pattern_start_date"], values["pattern_end_date"],
                values["surge_start_date"], values["surge_peak_date"],
                values["surge_return_5d"], values["observation_days"],
                values["weekly_shape_json"], values["sto_json"],
            ),
        )
        self.conn.execute(
            "DELETE FROM surge_pattern_bars WHERE pattern_id=?", (values["pattern_id"],)
        )
        base = float(bars.iloc[0]["Close"]) or 1.0
        self.conn.executemany(
            """
            INSERT INTO surge_pattern_bars(
                pattern_id, day_index, trade_date, open, high, low, close,
                volume, normalized_close
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    values["pattern_id"], idx,
                    str(pd.Timestamp(row["Date"]).date()),
                    float(row["Open"]), float(row["High"]), float(row["Low"]),
                    float(row["Close"]), float(row["Volume"]),
                    round((float(row["Close"]) / base - 1.0) * 100.0, 6),
                )
                for idx, (_, row) in enumerate(bars.iterrows())
            ],
        )

    def patterns(self, market: str, limit: int = 3000) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM surge_patterns
            WHERE market=? AND pattern_version=?
            ORDER BY surge_return_5d DESC, surge_start_date DESC
            LIMIT ?
            """,
            (market, PATTERN_VERSION, int(limit)),
        ).fetchall()

    def close(self) -> None:
        self.conn.close()


class SurgePatternBuilder:
    """Build 120-session patterns immediately before a one-week surge.

    A historical money explosion is only the observation anchor. After that event,
    the builder follows the stock for up to two trading years and finds distinct
    episodes where the next five sessions reach at least +30%. The 120 sessions
    ending immediately before that surge become the learning pattern.
    """

    def __init__(
        self,
        db_path: str | Path,
        price_source: str,
        source_money_ratio: float = 10.0,
        observation_days: int = 500,
        surge_days: int = 5,
        surge_return: float = 30.0,
        pattern_days: int = 120,
        cooldown_days: int = 20,
    ) -> None:
        self.db_path = Path(db_path)
        self.price_source = price_source
        self.source_money_ratio = float(source_money_ratio)
        self.observation_days = int(observation_days)
        self.surge_days = int(surge_days)
        self.surge_return = float(surge_return)
        self.pattern_days = int(pattern_days)
        self.cooldown_days = int(cooldown_days)
        self.price_repo = PriceRepository(self.db_path)
        self.repo = SurgePatternRepository(self.db_path)
        self.weekly_engine = WeeklyShapeSimilarityEngine(weeks=26)
        self.sto_engine = STOStructureSimilarityEngine()

    def close(self) -> None:
        self.price_repo.close()
        self.repo.close()

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
            for hit_no, hit in enumerate(hits, start=1):
                pattern_end = hit["start_index"] - 1
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
                    f"SURGE:{hit['start_date']}"
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
                    "surge_start_date": hit["start_date"],
                    "surge_peak_date": hit["peak_date"],
                    "surge_return_5d": hit["return_pct"],
                    "observation_days": hit["start_index"] - event_index,
                    "weekly_shape_json": json.dumps(weekly.to_dict(), ensure_ascii=False),
                    "sto_json": json.dumps(sto.to_dict(), ensure_ascii=False),
                }
                self.repo.upsert_pattern(values, window)
                patterns += 1
                pattern_bars += len(window)
            self.repo.conn.commit()
            print(
                f"[{index}/{len(events)}] {market.upper()}:{event['ticker']} "
                f"money={event['event_date']} surges={len(hits)}"
            )
        return SurgeBuildStats(len(events), patterns, pattern_bars)

    def _find_surges(self, df: pd.DataFrame, event_index: int) -> list[dict[str, object]]:
        start = max(event_index + 1, self.pattern_days)
        end = min(len(df) - self.surge_days, event_index + self.observation_days)
        hits: list[dict[str, object]] = []
        last_hit = -10_000
        for i in range(start, max(start, end)):
            if i - last_hit < self.cooldown_days:
                continue
            entry = float(df.iloc[i - 1]["Close"])
            if entry <= 0:
                continue
            future = df.iloc[i : i + self.surge_days]
            peak_offset = int(future["High"].astype(float).values.argmax())
            peak = float(future.iloc[peak_offset]["High"])
            return_pct = (peak / entry - 1.0) * 100.0
            if return_pct < self.surge_return:
                continue
            hits.append(
                {
                    "start_index": i,
                    "start_date": str(pd.Timestamp(df.iloc[i]["Date"]).date()),
                    "peak_date": str(pd.Timestamp(future.iloc[peak_offset]["Date"]).date()),
                    "return_pct": round(return_pct, 2),
                }
            )
            last_hit = i
        return hits

    @staticmethod
    def _prepare(data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        if "Date" not in df.columns:
            return pd.DataFrame()
        df["Date"] = pd.to_datetime(df["Date"])
        for column in ["Open", "High", "Low", "Close", "Volume"]:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        return df.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"]).sort_values("Date").reset_index(drop=True)

    @staticmethod
    def _date_index(df: pd.DataFrame, date_text: str) -> int | None:
        if df.empty:
            return None
        matches = df.index[df["Date"].dt.date.astype(str) == date_text].tolist()
        return int(matches[0]) if matches else None


class SurgePatternRecommender:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.price_repo = PriceRepository(self.db_path)
        self.repo = SurgePatternRepository(self.db_path)
        self.weekly_engine = WeeklyShapeSimilarityEngine(weeks=26)
        self.sto_engine = STOStructureSimilarityEngine()

    def close(self) -> None:
        self.repo.close()
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
        patterns = self.repo.patterns(market, limit=max(500, weekly_pool_n * 20))
        if not patterns:
            raise RuntimeError(
                "급등직전 패턴 DB가 없습니다. run_build_surge_patterns.py를 먼저 실행하세요."
            )
        prepared_patterns = [self._prepare_pattern(row) for row in patterns]
        prepared_patterns = [item for item in prepared_patterns if item is not None]
        results: list[EventRecommendation] = []
        for symbol in self._active_symbols(market):
            data = self.price_repo.fetch_dataframe(market, symbol["ticker"], source=source)
            current = data.tail(120).reset_index(drop=True)
            if len(current) < 120:
                continue
            current_weekly = self.weekly_engine.extract(current)
            current_sto = self.sto_engine.extract(current)
            matches: list[ReplayMatch] = []
            for row, weekly, sto in prepared_patterns:
                if row["ticker"] == symbol["ticker"] and row["pattern_end_date"] == str(pd.Timestamp(current.iloc[-1]["Date"]).date()):
                    continue
                chart_score = self.weekly_engine.similarity(current_weekly, weekly)
                if chart_score < min_weekly_similarity:
                    continue
                sto_score = self.sto_engine.similarity(current_sto, sto)
                if sto_score < min_sto_similarity:
                    continue
                final_score = min(chart_score, sto_score)
                matches.append(
                    ReplayMatch(
                        event_id=str(row["pattern_id"]),
                        event_date=str(row["surge_start_date"]),
                        market=str(row["market"]),
                        ticker=str(row["ticker"]),
                        name=row["name"],
                        weekly_similarity=chart_score,
                        sto_similarity=sto_score,
                        final_similarity=final_score,
                        max_return=float(row["surge_return_5d"]),
                        max_drawdown=None,
                        equivalent_week_index=25,
                        future_start_week_index=26,
                        weeks_compared=26,
                        future_weeks_available=1,
                    )
                )
            matches = sorted(
                matches,
                key=lambda item: (item.final_similarity, item.max_return or 0.0),
                reverse=True,
            )[:replay_top_n]
            if not matches:
                continue
            best = matches[0]
            average_surge = sum(float(item.max_return or 0.0) for item in matches) / len(matches)
            reasons = [
                "현재 최근 120거래일을 과거 급등직전 120거래일 패턴과 비교",
                f"차트 유사도 {best.weekly_similarity:.2f}% · STO 3계층 유사도 {best.sto_similarity:.2f}%",
                f"매칭 {len(matches)}건 · 매칭 사례 평균 5일 최고상승률 {average_surge:+.2f}%",
                f"Top1 과거 급등 시작일 {best.event_date} · 5일 최고상승률 {float(best.max_return or 0.0):+.2f}%",
            ]
            results.append(
                EventRecommendation(
                    market=market,
                    ticker=symbol["ticker"],
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
            )
        return sorted(
            results,
            key=lambda item: (
                item.final_similarity,
                len(item.replay_matches),
                item.matched_max_return or 0.0,
            ),
            reverse=True,
        )[:top_n]

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
