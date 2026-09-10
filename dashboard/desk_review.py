"""Human review belongs to one owner, one recommendation run and one ticker."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from core.run_models import content_hash, utc_now


@contextmanager
def _connection():
    path = Path(os.getenv("ADE_UI_STATE_DB", "output/ade_ui_state.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS decision_reviews (owner_id TEXT NOT NULL,market TEXT NOT NULL,"
            "run_id TEXT NOT NULL,ticker TEXT NOT NULL,evidence_hash TEXT NOT NULL,review_json TEXT NOT NULL,"
            "updated_at TEXT NOT NULL,PRIMARY KEY(owner_id,market,run_id,ticker))"
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_review(
    owner: str, market: str, run_id: str, ticker: str, evidence: dict, review: dict
) -> None:
    if not all((owner, market, run_id, ticker)):
        raise ValueError("검토할 추천 실행과 종목을 선택하세요.")
    with _connection() as conn:
        conn.execute(
            "INSERT INTO decision_reviews VALUES(?,?,?,?,?,?,?) ON CONFLICT(owner_id,market,run_id,ticker) "
            "DO UPDATE SET evidence_hash=excluded.evidence_hash,review_json=excluded.review_json,updated_at=excluded.updated_at",
            (
                owner,
                market,
                run_id,
                ticker,
                content_hash(evidence),
                json.dumps(review, ensure_ascii=False),
                utc_now(),
            ),
        )


def load_review(owner: str, market: str, run_id: str, ticker: str) -> dict:
    with _connection() as conn:
        row = conn.execute(
            "SELECT review_json FROM decision_reviews WHERE owner_id=? AND market=? AND run_id=? AND ticker=?",
            (owner, market, run_id, ticker),
        ).fetchone()
    return json.loads(row[0]) if row else {}
