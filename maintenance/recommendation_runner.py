from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any

from maintenance.job_manager import ADEJobManager
from recommendation.daily_service import DailyRecommendationService

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE_STATES = {"STARTING", "RUNNING", "CANCELLING"}
_HEARTBEAT_INTERVAL_SECONDS = 5
_STALE_AFTER_SECONDS = 30
_RUNTIME_DIR = Path(os.getenv("ADE_RUNTIME_DIR", "output"))
_STAGE_LABELS = {
    "STARTING": "작업 준비",
    "THREAD_STARTED": "작업 스레드 시작",
    "SERVICE_READY": "추천 서비스 준비",
    "LOCK_WAIT": "작업 잠금 확인",
    "ENGINE_START": "추천 엔진 시작",
    "PREPARE": "과거 패턴 준비",
    "MATCH": "전체 종목 비교",
    "RANK": "추천 순위 계산",
    "COMPLETE": "결과 저장",
    "CANCELLING": "중단 처리",
    "COMPLETED": "완료",
    "CANCELLED": "중단됨",
    "FAILED": "실패",
    "STALE": "비정상 종료",
}


def _status_path(market_code: str) -> Path:
    return _RUNTIME_DIR / f"{market_code}_recommendation_runtime.json"


def _history_path(market_code: str) -> Path:
    return _RUNTIME_DIR / f"{market_code}_recommendation_history.jsonl"


def _lock_path(market_code: str) -> Path:
    return _RUNTIME_DIR / f"{market_code}_recommendation.lock"


def _job_status_path(market_code: str) -> Path:
    return _RUNTIME_DIR / f"{market_code}_job_status.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _seconds_since(value: object) -> float | None:
    try:
        return max(0.0, (datetime.now() - datetime.fromisoformat(str(value))).total_seconds())
    except (TypeError, ValueError):
        return None


def _overall_progress(stage: str, stage_progress: float) -> float:
    value = min(1.0, max(0.0, float(stage_progress or 0.0)))
    if stage in {"STARTING", "THREAD_STARTED", "SERVICE_READY", "LOCK_WAIT", "ENGINE_START"}:
        return 0.02 * value
    if stage == "PREPARE":
        return 0.10 * value
    if stage == "MATCH":
        return 0.10 + 0.85 * value
    if stage in {"RANK", "COMPLETE"}:
        return 0.95 + 0.05 * value
    if stage == "COMPLETED":
        return 1.0
    return value


def _write_status(market_code: str, payload: dict[str, object]) -> dict[str, object]:
    path = _status_path(market_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    saved = {**payload, "updated_at": _now()}
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    return saved


def _append_history(market_code: str, payload: dict[str, object]) -> None:
    path = _history_path(market_code)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "market": market_code,
        "request_id": payload.get("request_id"),
        "run_id": payload.get("run_id"),
        "state": payload.get("state"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at") or _now(),
        "elapsed_seconds": payload.get("elapsed_seconds"),
        "recommendation_count": payload.get("recommendation_count"),
        "stage_durations": payload.get("stage_durations") or {},
        "diagnostics": payload.get("diagnostics") or {},
        "error_message": payload.get("error_message"),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _decorate_health(
    market_code: str,
    payload: dict[str, object],
    *,
    thread_alive: bool | None,
) -> dict[str, object]:
    snapshot = dict(payload)
    lock_exists = _lock_path(market_code).exists()
    heartbeat_age = _seconds_since(snapshot.get("heartbeat_at") or snapshot.get("updated_at"))
    snapshot["thread_alive"] = thread_alive
    snapshot["lock_exists"] = lock_exists
    snapshot["heartbeat_age_seconds"] = heartbeat_age
    snapshot["stage_label"] = _STAGE_LABELS.get(str(snapshot.get("stage") or ""), str(snapshot.get("stage") or "-"))

    state = str(snapshot.get("state") or "IDLE")
    if state in _ACTIVE_STATES:
        heartbeat_fresh = heartbeat_age is not None and heartbeat_age <= _STALE_AFTER_SECONDS
        if thread_alive is None:
            alive = lock_exists and heartbeat_fresh
        else:
            alive = thread_alive and lock_exists and heartbeat_fresh
        snapshot["running"] = alive
    else:
        snapshot["running"] = False
    return snapshot


def _recover_stale_status(market_code: str, payload: dict[str, object]) -> dict[str, object]:
    snapshot = _decorate_health(market_code, payload, thread_alive=None)
    state = str(snapshot.get("state") or "IDLE")
    if state not in _ACTIVE_STATES or bool(snapshot.get("running")):
        return snapshot

    recovered = {
        **snapshot,
        "state": "STALE",
        "stage": "STALE",
        "stage_label": _STAGE_LABELS["STALE"],
        "running": False,
        "message": "추천 작업의 생존 신호가 끊겨 비정상 종료 상태로 전환했습니다.",
        "error_message": "유효한 작업 스레드·잠금·heartbeat 조합을 확인하지 못했습니다.",
        "finished_at": _now(),
    }
    saved = _write_status(market_code, recovered)
    _append_history(market_code, saved)
    return saved


def get_status(market_code: str) -> dict[str, object]:
    with _LOCK:
        job = _JOBS.get(market_code)
        if job:
            thread = job.get("thread")
            snapshot = _decorate_health(
                market_code,
                dict(job.get("status", {})),
                thread_alive=bool(thread and thread.is_alive()),
            )
            return snapshot

    path = _status_path(market_code)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _recover_stale_status(market_code, payload)
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "state": "IDLE",
        "stage": "IDLE",
        "stage_label": "대기",
        "running": False,
        "progress": 0.0,
        "overall_progress": 0.0,
        "thread_alive": False,
        "lock_exists": False,
        "request_id": None,
    }


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
) -> str | None:
    with _LOCK:
        existing = _JOBS.get(market_code)
        if existing and existing.get("thread") and existing["thread"].is_alive():
            return None

        request_id = f"REQ-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        cancel_event = threading.Event()
        heartbeat_stop = threading.Event()
        started_at = _now()
        startup_trace: list[dict[str, str]] = [{"stage": "STARTING", "at": started_at}]
        initial = {
            "request_id": request_id,
            "state": "STARTING",
            "running": True,
            "stage": "STARTING",
            "stage_label": _STAGE_LABELS["STARTING"],
            "progress": 0.0,
            "stage_progress": 0.0,
            "overall_progress": 0.0,
            "current": 0,
            "total": 0,
            "current_ticker": None,
            "message": "추천 작업을 준비하고 있습니다.",
            "diagnostics": {},
            "stage_durations": {},
            "startup_trace": startup_trace,
            "started_at": started_at,
            "heartbeat_at": started_at,
        }
        initial = _write_status(market_code, initial)

        def heartbeat_worker() -> None:
            while not heartbeat_stop.wait(_HEARTBEAT_INTERVAL_SECONDS):
                with _LOCK:
                    job = _JOBS.get(market_code)
                    if not job:
                        return
                    status = dict(job.get("status", {}))
                    thread = job.get("thread")
                    if not thread or not thread.is_alive():
                        return
                    status["heartbeat_at"] = _now()
                    elapsed = _seconds_since(status.get("started_at"))
                    if elapsed is not None:
                        status["elapsed_seconds"] = elapsed
                    job["status"] = _write_status(market_code, status)

        def worker() -> None:
            stage_started_at = monotonic()
            last_stage: str | None = None
            stage_durations: dict[str, float] = {}
            service: DailyRecommendationService | None = None

            def publish_startup(stage: str, message: str) -> None:
                trace = [*startup_trace, {"stage": stage, "at": _now()}]
                startup_trace.clear()
                startup_trace.extend(trace)
                status = {
                    "request_id": request_id,
                    "state": "RUNNING",
                    "running": True,
                    "stage": stage,
                    "stage_label": _STAGE_LABELS[stage],
                    "progress": 0.0,
                    "stage_progress": 0.0,
                    "overall_progress": _overall_progress(stage, 0.0),
                    "current": 0,
                    "total": 0,
                    "current_ticker": None,
                    "message": message,
                    "diagnostics": {},
                    "stage_durations": dict(stage_durations),
                    "startup_trace": list(startup_trace),
                    "started_at": started_at,
                    "heartbeat_at": _now(),
                    "elapsed_seconds": _seconds_since(started_at) or 0.0,
                }
                with _LOCK:
                    if market_code in _JOBS:
                        _JOBS[market_code]["status"] = _write_status(market_code, status)

            publish_startup("THREAD_STARTED", "추천 작업 스레드를 시작했습니다.")
            service = DailyRecommendationService(db_path)
            publish_startup("SERVICE_READY", "추천 서비스 초기화를 완료했습니다.")
            manager = ADEJobManager(
                lock_path=_lock_path(market_code),
                status_path=_job_status_path(market_code),
            )

            def on_progress(progress: dict[str, object]) -> None:
                nonlocal stage_started_at, last_stage
                stage = str(progress.get("stage") or "RUNNING")
                now_mono = monotonic()
                if last_stage is None:
                    last_stage = stage
                    stage_started_at = now_mono
                elif stage != last_stage:
                    stage_durations[last_stage] = round(
                        stage_durations.get(last_stage, 0.0) + (now_mono - stage_started_at),
                        3,
                    )
                    last_stage = stage
                    stage_started_at = now_mono

                current = int(progress.get("current") or 0)
                total = int(progress.get("total") or 0)
                stage_progress = float(progress.get("progress") or 0.0)
                diagnostics = dict(progress.get("diagnostics") or {})
                ticker = progress.get("ticker")
                live_stage_durations = dict(stage_durations)
                if last_stage:
                    live_stage_durations[last_stage] = round(
                        live_stage_durations.get(last_stage, 0.0) + (now_mono - stage_started_at),
                        3,
                    )
                status = {
                    "request_id": request_id,
                    "state": "RUNNING",
                    "running": True,
                    **progress,
                    "stage": stage,
                    "stage_label": _STAGE_LABELS.get(stage, stage),
                    "stage_progress": stage_progress,
                    "overall_progress": _overall_progress(stage, stage_progress),
                    "current": current,
                    "total": total,
                    "processed_symbols": current if stage == "MATCH" else diagnostics.get("symbols_with_120d", 0),
                    "total_symbols": total if stage == "MATCH" else diagnostics.get("symbols_total", 0),
                    "remaining_symbols": max(0, total - current) if stage == "MATCH" else None,
                    "current_ticker": ticker,
                    "matched_symbols": diagnostics.get("symbols_with_matches", 0),
                    "stage_durations": live_stage_durations,
                    "startup_trace": list(startup_trace),
                    "started_at": started_at,
                    "heartbeat_at": _now(),
                    "elapsed_seconds": _seconds_since(started_at) or 0.0,
                }
                with _LOCK:
                    if market_code in _JOBS:
                        _JOBS[market_code]["status"] = _write_status(market_code, status)

            final: dict[str, object]
            try:
                publish_startup("LOCK_WAIT", "추천 작업 잠금을 확인하고 있습니다.")
                with manager.acquire(f"{market_code.upper()}_MANUAL_RECOMMENDATION", wait=False):
                    publish_startup("ENGINE_START", "추천 엔진 실행을 시작했습니다.")
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
                finished_mono = monotonic()
                if last_stage:
                    stage_durations[last_stage] = round(
                        stage_durations.get(last_stage, 0.0) + (finished_mono - stage_started_at),
                        3,
                    )
                finished_at = _now()
                final = {
                    "request_id": request_id,
                    "state": result.status,
                    "running": False,
                    "stage": result.status,
                    "stage_label": _STAGE_LABELS.get(result.status, result.status),
                    "progress": 1.0 if result.status == "COMPLETED" else 0.0,
                    "stage_progress": 1.0 if result.status == "COMPLETED" else 0.0,
                    "overall_progress": 1.0 if result.status == "COMPLETED" else 0.0,
                    "message": "추천 생성이 완료되었습니다." if result.status == "COMPLETED" else "사용자 요청으로 추천 생성을 중단했습니다.",
                    "run_id": result.run_id,
                    "recommendation_count": result.recommendation_count,
                    "elapsed_seconds": result.elapsed_seconds,
                    "stage_durations": stage_durations,
                    "startup_trace": list(startup_trace),
                    "report_path": result.report_path,
                    "diagnostics": result.diagnostics or {},
                    "error_message": result.error_message,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "heartbeat_at": finished_at,
                }
            except Exception as exc:
                finished_mono = monotonic()
                if last_stage:
                    stage_durations[last_stage] = round(
                        stage_durations.get(last_stage, 0.0) + (finished_mono - stage_started_at),
                        3,
                    )
                finished_at = _now()
                final = {
                    "request_id": request_id,
                    "state": "FAILED",
                    "running": False,
                    "stage": "FAILED",
                    "stage_label": _STAGE_LABELS["FAILED"],
                    "progress": 0.0,
                    "stage_progress": 0.0,
                    "overall_progress": 0.0,
                    "message": "추천 생성에 실패했습니다.",
                    "error_message": str(exc),
                    "diagnostics": {},
                    "stage_durations": stage_durations,
                    "startup_trace": list(startup_trace),
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "heartbeat_at": finished_at,
                    "elapsed_seconds": _seconds_since(started_at) or 0.0,
                }
            finally:
                if service is not None:
                    service.close()
                heartbeat_stop.set()

            with _LOCK:
                if market_code in _JOBS:
                    saved = _write_status(market_code, final)
                    _JOBS[market_code]["status"] = saved
                    _append_history(market_code, saved)

        thread = threading.Thread(target=worker, name=f"ade-{market_code}-recommendation", daemon=True)
        heartbeat = threading.Thread(target=heartbeat_worker, name=f"ade-{market_code}-heartbeat", daemon=True)
        _JOBS[market_code] = {
            "request_id": request_id,
            "thread": thread,
            "heartbeat_thread": heartbeat,
            "heartbeat_stop": heartbeat_stop,
            "cancel_event": cancel_event,
            "status": initial,
        }
        thread.start()
        heartbeat.start()
        return request_id


def cancel_job(market_code: str) -> bool:
    with _LOCK:
        job = _JOBS.get(market_code)
        if not job or not job.get("thread") or not job["thread"].is_alive():
            return False
        job["cancel_event"].set()
        status = dict(job.get("status", {}))
        status.update({
            "state": "CANCELLING",
            "stage": "CANCELLING",
            "stage_label": _STAGE_LABELS["CANCELLING"],
            "running": True,
            "heartbeat_at": _now(),
            "message": "현재 비교 작업을 마친 뒤 안전하게 중단합니다.",
        })
        job["status"] = _write_status(market_code, status)
    return True
