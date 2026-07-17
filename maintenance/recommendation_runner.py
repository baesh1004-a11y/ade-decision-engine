from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from maintenance.job_manager import ADEJobManager
from recommendation.daily_service import DailyRecommendationService

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def _status_path(market_code: str) -> Path:
    return Path(f"output/{market_code}_recommendation_runtime.json")


def _write_status(market_code: str, payload: dict[str, object]) -> None:
    path = _status_path(market_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**payload, "updated_at": datetime.now().isoformat(timespec="seconds")}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_status(market_code: str) -> dict[str, object]:
    with _LOCK:
        job = _JOBS.get(market_code)
        if job:
            snapshot = dict(job.get("status", {}))
            snapshot["running"] = bool(job.get("thread") and job["thread"].is_alive())
            return snapshot
    path = _status_path(market_code)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"state": "IDLE", "running": False, "progress": 0.0}


def start_job(
    market_code: str,
    db_path: str | Path,
    *,
    top_n: int,
    weekly_pool_n: int,
    candidate_years: int,
    use_recent_replay: bool,
    use_weekly_filter: bool,
    min_weekly_similarity: float,
    use_sto_filter: bool,
    min_sto_similarity: float,
) -> bool:
    with _LOCK:
        existing = _JOBS.get(market_code)
        if existing and existing.get("thread") and existing["thread"].is_alive():
            return False

        cancel_event = threading.Event()
        initial = {
            "state": "STARTING",
            "running": True,
            "stage": "STARTING",
            "progress": 0.0,
            "message": "추천 작업을 준비하고 있습니다.",
            "diagnostics": {},
        }
        _write_status(market_code, initial)

        def worker() -> None:
            service = DailyRecommendationService(db_path)
            manager = ADEJobManager(
                lock_path=f"output/{market_code}_recommendation.lock",
                status_path=f"output/{market_code}_job_status.json",
            )

            def on_progress(progress: dict[str, object]) -> None:
                status = {"state": "RUNNING", "running": True, **progress}
                with _LOCK:
                    if market_code in _JOBS:
                        _JOBS[market_code]["status"] = status
                _write_status(market_code, status)

            try:
                with manager.acquire(f"{market_code.upper()}_MANUAL_RECOMMENDATION", wait=False):
                    result = service.run(
                        "MANUAL",
                        top_n=top_n,
                        weekly_pool_n=weekly_pool_n,
                        candidate_years=candidate_years,
                        use_recent_replay=use_recent_replay,
                        use_weekly_filter=use_weekly_filter,
                        min_weekly_similarity=min_weekly_similarity,
                        use_sto_filter=use_sto_filter,
                        min_sto_similarity=min_sto_similarity,
                        progress_callback=on_progress,
                        cancel_check=cancel_event.is_set,
                    )
                final = {
                    "state": result.status,
                    "running": False,
                    "stage": result.status,
                    "progress": 1.0 if result.status == "COMPLETED" else 0.0,
                    "message": "추천 생성이 완료되었습니다." if result.status == "COMPLETED" else "사용자 요청으로 추천 생성을 중단했습니다.",
                    "run_id": result.run_id,
                    "recommendation_count": result.recommendation_count,
                    "elapsed_seconds": result.elapsed_seconds,
                    "report_path": result.report_path,
                    "diagnostics": result.diagnostics or {},
                    "error_message": result.error_message,
                }
            except Exception as exc:
                final = {
                    "state": "FAILED",
                    "running": False,
                    "stage": "FAILED",
                    "progress": 0.0,
                    "message": "추천 생성에 실패했습니다.",
                    "error_message": str(exc),
                    "diagnostics": {},
                }
            finally:
                service.close()

            with _LOCK:
                if market_code in _JOBS:
                    _JOBS[market_code]["status"] = final
            _write_status(market_code, final)

        thread = threading.Thread(target=worker, name=f"ade-{market_code}-recommendation", daemon=True)
        _JOBS[market_code] = {"thread": thread, "cancel_event": cancel_event, "status": initial}
        thread.start()
        return True


def cancel_job(market_code: str) -> bool:
    with _LOCK:
        job = _JOBS.get(market_code)
        if not job or not job.get("thread") or not job["thread"].is_alive():
            return False
        job["cancel_event"].set()
        status = dict(job.get("status", {}))
        status.update({
            "state": "CANCELLING",
            "running": True,
            "message": "현재 비교 작업을 마친 뒤 안전하게 중단합니다.",
        })
        job["status"] = status
    _write_status(market_code, status)
    return True
