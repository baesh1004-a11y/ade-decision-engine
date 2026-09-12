import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from core.run_models import RunRequest
from maintenance import recommendation_runner as runner
from maintenance.job_manager import ADEJobManager
from recommendation.daily_service import DailyRecommendationService

OPTIONS = dict(
    top_n=2,
    weekly_pool_n=100,
    candidate_years=2,
    use_recent_replay=True,
    use_weekly_filter=True,
    min_weekly_similarity=85,
    use_sto_filter=True,
    min_sto_similarity=85,
)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(runner, "_JOBS", {})
    return tmp_path


def interrupted(runtime, *, stage_started=True):
    path = runtime / "market.db"
    service = DailyRecommendationService(path)
    with service.conn:
        service.conn.execute(
            "INSERT INTO recommendation_runs(run_id,run_type,trading_date,started_at,status,parameters_json,market) "
            "VALUES('lost','MANUAL','2026-09-12','2026-09-12','RUNNING','{}','kr')"
        )
        service.run_store.create(
            RunRequest(kind="recommendation", market="kr", run_id="lost"),
            ("RECOMMEND", "PERSIST"),
        )
    if stage_started:
        service.run_store.start("lost")
        service.run_store.start_stage("lost", "RECOMMEND")
    service.close()
    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    runner._write_status(
        "kr",
        {
            "request_id": "lost-request",
            "run_id": "lost",
            "db_path": str(path),
            "state": "RUNNING",
            "stage": "MATCH",
            "heartbeat_at": old,
        },
    )
    return path


@pytest.mark.parametrize("stage_started", [True, False])
def test_dead_worker_recovery_updates_both_ledgers_once(runtime, stage_started):
    path = interrupted(runtime, stage_started=stage_started)
    assert runner.get_status("kr")["state"] == "STALE"
    assert runner.get_status("kr")["state"] == "STALE"
    service = DailyRecommendationService(path)
    try:
        assert (
            service.conn.execute(
                "SELECT status FROM recommendation_runs WHERE run_id='lost'"
            ).fetchone()[0]
            == "FAILED"
        )
        recorded = service.run_store.get("lost")
        assert recorded.status == "FAILED"
        assert all(stage.status in {"FAILED", "SKIPPED"} for stage in recorded.stages)
        if not stage_started:
            assert all(stage.started_at is None for stage in recorded.stages)
    finally:
        service.close()
    assert len(runner._history_path("kr").read_text().splitlines()) == 1


def test_held_os_lock_prevents_recovery_and_second_worker_even_with_old_heartbeat(
    runtime,
):
    path = interrupted(runtime)
    manager = ADEJobManager(runner._lock_path("kr"), runner._job_status_path("kr"))
    with manager.acquire("test-worker", wait=False):
        before = runner._status_path("kr").read_text()
        assert runner.get_status("kr")["running"]
        assert runner.start_job("kr", path, **OPTIONS) is None
        assert runner._status_path("kr").read_text() == before
    assert runner.get_status("kr")["state"] == "STALE"


def test_committed_results_win_over_stale_runtime_file(runtime):
    path = interrupted(runtime)
    service = DailyRecommendationService(path)
    try:
        with service.conn:
            service.run_store.complete_stage("lost", "RECOMMEND")
            service.run_store.start_stage("lost", "PERSIST")
            service.run_store.complete_stage("lost", "PERSIST")
            service.run_store.finish("lost")
            service.conn.execute(
                "UPDATE recommendation_runs SET status='COMPLETED', recommendation_count=0 WHERE run_id='lost'"
            )
    finally:
        service.close()
    status = runner.get_status("kr")
    assert status["state"] == "COMPLETED"
    assert status["recommendation_count"] == 0
    assert status["overall_progress"] == 1


def test_service_initialization_failure_is_terminal_and_releases_worker_lock(
    runtime, monkeypatch
):
    def broken(*args, **kwargs):
        raise OSError("database unavailable")

    monkeypatch.setattr(runner, "DailyRecommendationService", broken)
    assert runner.start_job("kr", runtime / "market.db", **OPTIONS)
    runner._JOBS["kr"]["thread"].join(timeout=5)
    assert not runner._JOBS["kr"]["thread"].is_alive()
    status = runner.get_status("kr")
    assert status["state"] == "FAILED"
    assert "database unavailable" in status["error_message"]
    assert runner._JOBS["kr"]["heartbeat_stop"].is_set()
    manager = ADEJobManager(runner._lock_path("kr"), runner._job_status_path("kr"))
    with manager.acquire("next-worker", wait=False):
        pass


def test_atomic_runtime_file_and_local_live_thread_do_not_false_recover(runtime):
    entered, release = threading.Event(), threading.Event()

    def hold():
        entered.set()
        release.wait(timeout=5)

    thread = threading.Thread(target=hold)
    thread.start()
    entered.wait(timeout=2)
    try:
        old = "2001-01-01T00:00:00+00:00"
        payload = runner._write_status("kr", {"state": "RUNNING", "heartbeat_at": old})
        runner._JOBS["kr"] = {"thread": thread, "status": payload}
        assert runner.get_status("kr")["running"]
        assert json.loads(runner._status_path("kr").read_text())["state"] == "RUNNING"
        assert not list(runner._RUNTIME_DIR.glob("*.tmp"))
    finally:
        release.set()
        thread.join(timeout=5)


def test_finished_local_job_does_not_hide_another_process_new_job(runtime):
    path = interrupted(runtime)
    runner._JOBS["kr"] = {
        "thread": threading.Thread(),
        "status": {"request_id": "older-local-request", "state": "COMPLETED"},
    }
    manager = ADEJobManager(runner._lock_path("kr"), runner._job_status_path("kr"))
    with manager.acquire("other-process", wait=False):
        status = runner.get_status("kr")
        assert status["request_id"] == "lost-request"
        assert status["running"]
        assert runner.start_job("kr", path, **OPTIONS) is None


def test_background_worker_publishes_run_identity_before_engine_and_finishes(
    runtime, monkeypatch
):
    from recommendation import daily_service

    seen = []

    class Engine:
        def __init__(self, path):
            seen.append(runner._read_status("kr")["run_id"])

        def recommend_interactive(self, **kwargs):
            kwargs["progress_callback"]({"stage": "MATCH", "progress": 0.5})
            return [], {}

        def close(self):
            pass

    monkeypatch.setattr(daily_service, "InteractiveSurgePatternRecommender", Engine)
    monkeypatch.setattr(
        daily_service, "runtime_path", lambda *parts: runtime.joinpath(*parts)
    )
    assert runner.start_job("kr", runtime / "market.db", **OPTIONS)
    runner._JOBS["kr"]["thread"].join(timeout=5)
    status = runner.get_status("kr")
    assert not runner._JOBS["kr"]["thread"].is_alive()
    assert status["state"] == "COMPLETED"
    assert status["run_id"] == seen[0]
    service = DailyRecommendationService(runtime / "market.db")
    try:
        assert service.run_store.get(status["run_id"]).status == "SUCCEEDED"
    finally:
        service.close()
