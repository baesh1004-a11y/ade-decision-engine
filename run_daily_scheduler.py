from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, time as clock_time
from pathlib import Path

from maintenance.job_manager import ADEJobManager
from recommendation.daily_service import DailyRecommendationService


HEARTBEAT_PATH = Path("output/ade_core_status.json")


def _write_heartbeat(status: str, schedule: str, message: str = "") -> None:
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "pid": os.getpid(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "schedule": schedule,
        "message": message,
    }
    HEARTBEAT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ADE automatic post-close recommendations")
    parser.add_argument("--hour", type=int, default=16)
    parser.add_argument("--minute", type=int, default=10)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--weekly-pool", type=int, default=100)
    parser.add_argument("--min-weekly", type=float, default=85.0)
    parser.add_argument("--min-sto", type=float, default=85.0)
    args = parser.parse_args()

    target_time = clock_time(args.hour, args.minute)
    schedule_text = f"weekdays {args.hour:02d}:{args.minute:02d}"
    print("========================================")
    print(" ADE CORE")
    print("========================================")
    print(f"Schedule : {schedule_text}")
    print(f"Poll     : every {args.poll_seconds}s")
    _write_heartbeat("RUNNING", schedule_text, "ADE Core started")

    try:
        while True:
            now = datetime.now()
            _write_heartbeat("RUNNING", schedule_text, "Waiting for schedule")
            should_run = now.weekday() < 5 and now.time() >= target_time
            if should_run:
                service = DailyRecommendationService()
                try:
                    if not service.auto_completed_today():
                        _write_heartbeat("RUNNING", schedule_text, "AUTO recommendation queued")
                        print(f"[{now.isoformat(timespec='seconds')}] AUTO recommendation queued...")
                        with ADEJobManager().acquire(
                            "AUTO_RECOMMENDATION",
                            wait=True,
                            timeout_seconds=6 * 60 * 60,
                        ):
                            result = service.run(
                                "AUTO",
                                top_n=args.top,
                                weekly_pool_n=args.weekly_pool,
                                min_weekly_similarity=args.min_weekly,
                                min_sto_similarity=args.min_sto,
                            )
                        message = (
                            f"AUTO completed: {result.recommendation_count} recommendations, "
                            f"{result.elapsed_seconds:.1f}s"
                        )
                        print(f"[{result.finished_at}] {message}")
                        _write_heartbeat("RUNNING", schedule_text, message)
                except Exception as exc:
                    message = f"AUTO failed: {exc}"
                    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}")
                    _write_heartbeat("ERROR", schedule_text, message)
                finally:
                    service.close()
            time.sleep(max(10, args.poll_seconds))
    except KeyboardInterrupt:
        _write_heartbeat("STOPPED", schedule_text, "ADE Core stopped by user")
        print("ADE Core stopped")


if __name__ == "__main__":
    main()
