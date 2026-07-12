from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter

from recommendation.event_recommender import RecentMoneyEventRecommender
from report.recommendation_html_report import render_recommendation_html


@dataclass(frozen=True)
class RecommendationRunResult:
    run_id: str
    run_type: str
    started_at: str
    finished_at: str
    recommendation_count: int
    elapsed_seconds: float
    report_path: str
    status: str
    error_message: str | None = None


class DailyRecommendationService:
    """Run one recommendation engine for both scheduled and dashboard-triggered jobs."""

    _process_lock = threading.Lock()

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendation_runs (
                run_id TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                trading_date TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                recommendation_count INTEGER NOT NULL DEFAULT 0,
                elapsed_seconds REAL,
                report_path TEXT,
                parameters_json TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_recommendations (
                run_id TEXT NOT NULL,
                rank_no INTEGER NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                decision TEXT NOT NULL,
                final_similarity REAL NOT NULL,
                weekly_similarity REAL NOT NULL,
                sto_similarity REAL NOT NULL,
                prediction_grade TEXT,
                seven_day_up_probability REAL,
                seven_day_expected_return REAL,
                target_return REAL,
                stop_return REAL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, rank_no)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recommendation_runs_date ON recommendation_runs(trading_date, run_type, status)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_daily_recommendations_ticker ON daily_recommendations(market, ticker)"
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def run(
        self,
        run_type: str,
        candidate_years: int = 2,
        lookback_months: int = 6,
        top_n: int = 20,
        weekly_pool_n: int = 100,
        min_weekly_similarity: float = 85.0,
        min_sto_similarity: float = 85.0,
        replay_top_n: int = 5,
    ) -> RecommendationRunResult:
        normalized_type = run_type.strip().upper()
        if normalized_type not in {"AUTO", "MANUAL"}:
            raise ValueError("run_type must be AUTO or MANUAL")
        if not self._process_lock.acquire(blocking=False):
            raise RuntimeError("Another recommendation job is already running")

        run_id = f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-{normalized_type}-{uuid.uuid4().hex[:8]}"
        started = datetime.now()
        parameters = {
            "candidate_years": candidate_years,
            "lookback_months": lookback_months,
            "top_n": top_n,
            "weekly_pool_n": weekly_pool_n,
            "min_weekly_similarity": min_weekly_similarity,
            "min_sto_similarity": min_sto_similarity,
            "replay_top_n": replay_top_n,
        }
        self.conn.execute(
            """
            INSERT INTO recommendation_runs(
                run_id, run_type, trading_date, started_at, status, parameters_json
            ) VALUES (?, ?, ?, ?, 'RUNNING', ?)
            """,
            (
                run_id,
                normalized_type,
                started.date().isoformat(),
                started.isoformat(timespec="seconds"),
                json.dumps(parameters, ensure_ascii=False),
            ),
        )
        self.conn.commit()

        timer = perf_counter()
        try:
            engine = RecentMoneyEventRecommender(self.db_path)
            try:
                recommendations = engine.recommend(
                    candidate_years=candidate_years,
                    lookback_months=lookback_months,
                    top_n=top_n,
                    weekly_pool_n=weekly_pool_n,
                    min_weekly_similarity=min_weekly_similarity,
                    min_sto_similarity=min_sto_similarity,
                    replay_top_n=replay_top_n,
                )
            finally:
                engine.close()

            report_path = Path("output/daily_recommendations") / f"{run_id}.html"
            report_path = render_recommendation_html(
                recommendations,
                report_path,
                lookback_months=lookback_months,
            )
            for rank_no, item in enumerate(recommendations, start=1):
                prediction = item.prediction
                self.conn.execute(
                    """
                    INSERT INTO daily_recommendations(
                        run_id, rank_no, market, ticker, name, decision,
                        final_similarity, weekly_similarity, sto_similarity,
                        prediction_grade, seven_day_up_probability,
                        seven_day_expected_return, target_return, stop_return,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        rank_no,
                        item.market,
                        item.ticker,
                        item.name,
                        item.decision,
                        item.final_similarity,
                        item.weekly_similarity,
                        item.sto_similarity,
                        prediction.grade if prediction else None,
                        prediction.seven_day_up_probability if prediction else None,
                        prediction.seven_day_expected_return if prediction else None,
                        prediction.target_return if prediction else None,
                        prediction.stop_return if prediction else None,
                        json.dumps(item.to_dict(), ensure_ascii=False),
                    ),
                )

            finished = datetime.now()
            elapsed = perf_counter() - timer
            self.conn.execute(
                """
                UPDATE recommendation_runs
                SET finished_at=?, status='COMPLETED', recommendation_count=?,
                    elapsed_seconds=?, report_path=?
                WHERE run_id=?
                """,
                (
                    finished.isoformat(timespec="seconds"),
                    len(recommendations),
                    elapsed,
                    str(report_path),
                    run_id,
                ),
            )
            self.conn.commit()
            return RecommendationRunResult(
                run_id=run_id,
                run_type=normalized_type,
                started_at=started.isoformat(timespec="seconds"),
                finished_at=finished.isoformat(timespec="seconds"),
                recommendation_count=len(recommendations),
                elapsed_seconds=elapsed,
                report_path=str(report_path),
                status="COMPLETED",
            )
        except Exception as exc:
            finished = datetime.now()
            elapsed = perf_counter() - timer
            self.conn.execute(
                """
                UPDATE recommendation_runs
                SET finished_at=?, status='FAILED', elapsed_seconds=?, error_message=?
                WHERE run_id=?
                """,
                (finished.isoformat(timespec="seconds"), elapsed, str(exc), run_id),
            )
            self.conn.commit()
            raise
        finally:
            self._process_lock.release()

    def auto_completed_today(self) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM recommendation_runs
            WHERE trading_date=? AND run_type='AUTO' AND status='COMPLETED'
            LIMIT 1
            """,
            (datetime.now().date().isoformat(),),
        ).fetchone()
        return row is not None

    def latest_runs(self, limit: int = 30) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """
            SELECT run_id, run_type, trading_date, started_at, finished_at, status,
                   recommendation_count, elapsed_seconds, report_path, error_message
            FROM recommendation_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    def recommendations_for_run(self, run_id: str) -> list[dict[str, object]]:
        rows = self.conn.execute(
            """
            SELECT rank_no, market, ticker, name, decision, final_similarity,
                   weekly_similarity, sto_similarity, prediction_grade,
                   seven_day_up_probability, seven_day_expected_return,
                   target_return, stop_return
            FROM daily_recommendations
            WHERE run_id=?
            ORDER BY rank_no
            """,
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]
