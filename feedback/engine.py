from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from datahub.repository import PriceRepository


@dataclass(frozen=True)
class FeedbackSummary:
    total: int
    completed: int
    success_count: int
    hit_rate: float
    avg_7d_return: float
    avg_max_return: float
    avg_min_return: float
    avg_prediction_error: float
    avg_peak_day_error: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class FeedbackEngine:
    """Track Meta Score snapshots and validate them against realized prices."""

    def __init__(self, db_path: str | Path = "datahub/market.db") -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.price_repo = PriceRepository(self.db_path)
        self.initialize()

    def initialize(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                market TEXT NOT NULL,
                ticker TEXT NOT NULL,
                name TEXT,
                decision TEXT NOT NULL,
                grade TEXT NOT NULL,
                meta_score REAL NOT NULL,
                replay_score REAL NOT NULL,
                prediction_score REAL NOT NULL,
                jp_radar_score REAL NOT NULL,
                market_score REAL NOT NULL,
                sector_score REAL NOT NULL,
                risk_score REAL NOT NULL,
                predicted_7d_up_probability REAL,
                predicted_7d_return REAL,
                predicted_peak_day REAL,
                target_return REAL,
                stop_return REAL,
                entry_price REAL,
                entry_trade_date TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                actual_7d_return REAL,
                actual_max_return REAL,
                actual_min_return REAL,
                actual_peak_day INTEGER,
                prediction_error REAL,
                peak_day_error REAL,
                success INTEGER,
                completed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_date, market, ticker)
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                trade_date TEXT NOT NULL,
                day_no INTEGER NOT NULL,
                close REAL NOT NULL,
                return_rate REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(case_id, trade_date),
                FOREIGN KEY(case_id) REFERENCES feedback_cases(id)
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_cases_status ON feedback_cases(status, snapshot_date)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_daily_case ON feedback_daily(case_id, day_no)")
        self.conn.commit()

    def close(self) -> None:
        self.price_repo.close()
        self.conn.close()

    def register_meta_results(self, results: Iterable[object], snapshot_date: str | None = None) -> int:
        snapshot = snapshot_date or date.today().isoformat()
        inserted = 0
        for item in results:
            market = str(getattr(item, "market_code", "kr")).lower()
            ticker = str(getattr(item, "ticker", ""))
            if not ticker:
                continue
            entry_trade_date, entry_price = self._entry_price(market, ticker, snapshot)
            breakdown = getattr(item, "breakdown", None)
            cursor = self.conn.execute(
                """
                INSERT INTO feedback_cases (
                    snapshot_date, market, ticker, name, decision, grade, meta_score,
                    replay_score, prediction_score, jp_radar_score, market_score,
                    sector_score, risk_score, predicted_7d_up_probability,
                    predicted_7d_return, predicted_peak_day, target_return, stop_return,
                    entry_price, entry_trade_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_date, market, ticker) DO NOTHING
                """,
                (
                    snapshot, market, ticker, getattr(item, "name", None),
                    str(getattr(item, "decision", "")), str(getattr(item, "grade", "")),
                    float(getattr(item, "meta_score", 0.0) or 0.0),
                    float(getattr(breakdown, "replay", 0.0) or 0.0),
                    float(getattr(breakdown, "prediction", 0.0) or 0.0),
                    float(getattr(breakdown, "jp_radar", 0.0) or 0.0),
                    float(getattr(breakdown, "market", 0.0) or 0.0),
                    float(getattr(breakdown, "sector", 0.0) or 0.0),
                    float(getattr(breakdown, "risk", 0.0) or 0.0),
                    getattr(item, "seven_day_up_probability", None),
                    getattr(item, "seven_day_expected_return", None),
                    getattr(item, "expected_peak_day", None),
                    getattr(item, "target_return", None),
                    getattr(item, "stop_return", None),
                    entry_price, entry_trade_date,
                ),
            )
            inserted += max(0, cursor.rowcount)
        self.conn.commit()
        return inserted

    def update_open_cases(self) -> int:
        cases = self.conn.execute("SELECT * FROM feedback_cases WHERE status='OPEN' ORDER BY snapshot_date").fetchall()
        completed = 0
        for case in cases:
            if not case["entry_price"] or not case["entry_trade_date"]:
                continue
            df = self.price_repo.fetch_dataframe(
                str(case["market"]),
                str(case["ticker"]),
                start_date=str(case["entry_trade_date"]),
                source="fdr",
            )
            if df.empty:
                df = self.price_repo.fetch_dataframe(
                    str(case["market"]),
                    str(case["ticker"]),
                    start_date=str(case["entry_trade_date"]),
                )
            if df.empty:
                continue
            frame = df.copy()
            frame["Date"] = pd.to_datetime(frame["Date"])
            frame = frame.sort_values("Date").reset_index(drop=True)
            frame = frame[frame["Date"].dt.date.astype(str) >= str(case["entry_trade_date"])].head(8)
            entry = float(case["entry_price"])
            for idx, row in frame.iterrows():
                trade_date = pd.Timestamp(row["Date"]).date().isoformat()
                close = float(row["Close"])
                ret = 0.0 if entry <= 0 else (close / entry - 1.0) * 100.0
                self.conn.execute(
                    """
                    INSERT INTO feedback_daily(case_id, trade_date, day_no, close, return_rate)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(case_id, trade_date) DO UPDATE SET
                        day_no=excluded.day_no, close=excluded.close, return_rate=excluded.return_rate
                    """,
                    (int(case["id"]), trade_date, int(idx), close, ret),
                )
            if len(frame) >= 8:
                self._complete_case(int(case["id"]))
                completed += 1
        self.conn.commit()
        return completed

    def summary(self) -> FeedbackSummary:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS success_count,
                AVG(CASE WHEN status='COMPLETED' THEN actual_7d_return END) AS avg_7d_return,
                AVG(CASE WHEN status='COMPLETED' THEN actual_max_return END) AS avg_max_return,
                AVG(CASE WHEN status='COMPLETED' THEN actual_min_return END) AS avg_min_return,
                AVG(CASE WHEN status='COMPLETED' THEN ABS(prediction_error) END) AS avg_prediction_error,
                AVG(CASE WHEN status='COMPLETED' THEN ABS(peak_day_error) END) AS avg_peak_day_error
            FROM feedback_cases
            """
        ).fetchone()
        completed = int(row["completed"] or 0)
        success = int(row["success_count"] or 0)
        return FeedbackSummary(
            total=int(row["total"] or 0),
            completed=completed,
            success_count=success,
            hit_rate=0.0 if completed == 0 else success / completed * 100.0,
            avg_7d_return=float(row["avg_7d_return"] or 0.0),
            avg_max_return=float(row["avg_max_return"] or 0.0),
            avg_min_return=float(row["avg_min_return"] or 0.0),
            avg_prediction_error=float(row["avg_prediction_error"] or 0.0),
            avg_peak_day_error=float(row["avg_peak_day_error"] or 0.0),
        )

    def cases_dataframe(self) -> pd.DataFrame:
        rows = self.conn.execute("SELECT * FROM feedback_cases ORDER BY snapshot_date DESC, meta_score DESC").fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def daily_dataframe(self, case_id: int) -> pd.DataFrame:
        rows = self.conn.execute(
            "SELECT trade_date, day_no, close, return_rate FROM feedback_daily WHERE case_id=? ORDER BY day_no",
            (case_id,),
        ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def bucket_stats(self, column: str, buckets: list[tuple[str, float, float]]) -> pd.DataFrame:
        allowed = {"meta_score", "replay_score", "prediction_score", "jp_radar_score", "risk_score"}
        if column not in allowed:
            raise ValueError(f"Unsupported feedback column: {column}")
        rows: list[dict[str, object]] = []
        for label, low, high in buckets:
            data = self.conn.execute(
                f"""
                SELECT COUNT(*) AS cnt,
                       SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS success,
                       AVG(actual_7d_return) AS avg_return
                FROM feedback_cases
                WHERE status='COMPLETED' AND {column} >= ? AND {column} < ?
                """,
                (low, high),
            ).fetchone()
            cnt = int(data["cnt"] or 0)
            success = int(data["success"] or 0)
            rows.append(
                {
                    "bucket": label,
                    "count": cnt,
                    "success": success,
                    "hit_rate": 0.0 if cnt == 0 else success / cnt * 100.0,
                    "avg_7d_return": float(data["avg_return"] or 0.0),
                }
            )
        return pd.DataFrame(rows)

    def _complete_case(self, case_id: int) -> None:
        case = self.conn.execute("SELECT * FROM feedback_cases WHERE id=?", (case_id,)).fetchone()
        daily = self.conn.execute(
            "SELECT day_no, return_rate FROM feedback_daily WHERE case_id=? ORDER BY day_no LIMIT 8",
            (case_id,),
        ).fetchall()
        if case is None or len(daily) < 8:
            return
        returns = [float(row["return_rate"]) for row in daily]
        actual_7d = returns[7]
        max_return = max(returns)
        min_return = min(returns)
        peak_day = max(range(len(returns)), key=lambda idx: returns[idx])
        predicted_return = case["predicted_7d_return"]
        predicted_peak = case["predicted_peak_day"]
        prediction_error = None if predicted_return is None else actual_7d - float(predicted_return)
        peak_error = None if predicted_peak is None else peak_day - float(predicted_peak)
        success = 1 if actual_7d > 0 else 0
        self.conn.execute(
            """
            UPDATE feedback_cases
            SET status='COMPLETED', actual_7d_return=?, actual_max_return=?, actual_min_return=?,
                actual_peak_day=?, prediction_error=?, peak_day_error=?, success=?, completed_at=?
            WHERE id=?
            """,
            (
                actual_7d, max_return, min_return, peak_day,
                prediction_error, peak_error, success,
                datetime.now().isoformat(timespec="seconds"), case_id,
            ),
        )

    def _entry_price(self, market: str, ticker: str, snapshot_date: str) -> tuple[str | None, float | None]:
        df = self.price_repo.fetch_dataframe(market, ticker, start_date=snapshot_date, source="fdr")
        if df.empty:
            df = self.price_repo.fetch_dataframe(market, ticker, start_date=snapshot_date)
        if df.empty:
            return None, None
        row = df.iloc[0]
        return pd.Timestamp(row["Date"]).date().isoformat(), float(row["Close"])
