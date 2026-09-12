"""Reconcile a runner's exact run after its OS worker lock has been acquired."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.run_models import utc_now
from core.run_state_store import RunStateStore
from recommendation.evidence import table_exists

INTERRUPTED = "추천 작업이 종료되어 실행을 중단 상태로 정리했습니다. 새 계산을 시작할 수 있습니다."


def reconcile_interrupted_run(payload: dict, market: str) -> dict:
    """Caller MUST hold the same exclusive OS lock used by recommendation workers.

    Reconciles one recorded run, never orders or unrelated API/scheduled runs.
    A committed result wins over a stale runtime file after a process crash.
    """
    path = payload.get("db_path")
    run_id = payload.get("run_id")
    if not path or not run_id or not Path(str(path)).is_file():
        return {"state": "STALE", "error_message": INTERRUPTED}
    conn = sqlite3.connect(
        Path(str(path)).resolve().as_uri() + "?mode=rw", uri=True, timeout=5
    )
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "recommendation_runs"):
            return {"state": "STALE", "error_message": INTERRUPTED}
        store = RunStateStore(conn)
        with store.atomic():
            row = conn.execute(
                "SELECT * FROM recommendation_runs WHERE run_id=? AND market=?",
                (run_id, market),
            ).fetchone()
            if row is None:
                return {"state": "STALE", "error_message": INTERRUPTED}
            if row["status"] in {"COMPLETED", "CANCELLED", "FAILED"}:
                return {
                    "state": row["status"],
                    "run_id": run_id,
                    "recommendation_count": row["recommendation_count"],
                    "finished_at": row["finished_at"],
                    "report_path": row["report_path"],
                    "error_message": row["error_message"],
                }
            recorded = conn.execute(
                "SELECT status FROM ade_runs WHERE run_id=? AND market=? AND kind='recommendation'",
                (run_id, market),
            ).fetchone()
            if recorded and recorded["status"] in {"CREATED", "VALIDATING", "RUNNING"}:
                store.finish(run_id, "FAILED", INTERRUPTED)
            elif recorded:
                # Preserve an already terminal ledger. Do not invent a new outcome.
                if recorded["status"] not in {"FAILED", "CANCELLED"}:
                    raise ValueError(
                        "추천 완료 상태와 실행 기록이 다릅니다. 결과 확인이 필요합니다."
                    )
            state = (
                recorded["status"]
                if recorded and recorded["status"] == "CANCELLED"
                else "FAILED"
            )
            conn.execute(
                "UPDATE recommendation_runs SET status=?,finished_at=?,error_message=? "
                "WHERE run_id=? AND market=? AND status='RUNNING'",
                (state, utc_now(), INTERRUPTED, run_id, market),
            )
        return {"state": "STALE", "run_id": run_id, "error_message": INTERRUPTED}
    finally:
        conn.close()
