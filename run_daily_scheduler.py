from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, time as clock_time
from pathlib import Path
from zoneinfo import ZoneInfo

from dashboard.system_status import inspect_market_db
from maintenance.job_manager import ADEJobManager
from markets.profiles import get_market_profile
from recommendation.daily_service import DailyRecommendationService


def _write_heartbeat(path: Path, status: str, schedule: str, market: str, message: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "market": market,
        "pid": os.getpid(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "schedule": schedule,
        "message": message,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ADE automatic post-close recommendations")
    parser.add_argument("--market", choices=["kr", "us"], default="kr")
    parser.add_argument("--hour", type=int)
    parser.add_argument("--minute", type=int)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--weekly-pool", type=int, default=100)
    parser.add_argument("--min-weekly", type=float, default=85.0)
    parser.add_argument("--min-sto", type=float, default=85.0)
    args = parser.parse_args()

    profile = get_market_profile(args.market)
    default_hour, default_minute = (16, 10) if profile.code == "kr" else (16, 20)
    hour = default_hour if args.hour is None else args.hour
    minute = default_minute if args.minute is None else args.minute
    target_time = clock_time(hour, minute)
    timezone = ZoneInfo(profile.timezone)
    schedule_text = f"weekdays {hour:02d}:{minute:02d} {profile.timezone}"
    heartbeat_path = Path(f"output/{profile.code}_core_status.json")

    print("========================================")
    print(f" ADE {profile.code.upper()} CORE")
    print("========================================")
    print(f"Database : {profile.db_path}")
    print(f"Schedule : {schedule_text}")
    print(f"Poll     : every {args.poll_seconds}s")
    _write_heartbeat(heartbeat_path, "RUNNING", schedule_text, profile.code, "ADE Core started")

    try:
        while True:
            now = datetime.now(timezone)
            _write_heartbeat(heartbeat_path, "RUNNING", schedule_text, profile.code, "Waiting for schedule")
            should_run = now.weekday() < 5 and now.time().replace(tzinfo=None) >= target_time
            if should_run:
                readiness = inspect_market_db(profile.db_path, profile.code)
                if not readiness.ready:
                    message = "AUTO blocked: " + " / ".join(readiness.issues)
                    print(f"[{now.isoformat(timespec='seconds')}] {message}")
                    _write_heartbeat(heartbeat_path, "BLOCKED", schedule_text, profile.code, message)
                    time.sleep(max(10, args.poll_seconds))
                    continue

                service = DailyRecommendationService(profile.db_path)
                try:
                    if not service.auto_completed_today():
                        _write_heartbeat(heartbeat_path, "RUNNING", schedule_text, profile.code, "AUTO recommendation queued")
                        print(f"[{now.isoformat(timespec='seconds')}] AUTO recommendation queued...")
                        with ADEJobManager(
                            lock_path=f"output/{profile.code}_recommendation.lock",
                            status_path=f"output/{profile.code}_job_status.json",
                        ).acquire(
                            f"{profile.code.upper()}_AUTO_RECOMMENDATION",
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
                        message = f"AUTO completed: {result.recommendation_count} recommendations, {result.elapsed_seconds:.1f}s"
                        print(f"[{result.finished_at}] {message}")
                        _write_heartbeat(heartbeat_path, "RUNNING", schedule_text, profile.code, message)
                except Exception as exc:
                    message = f"AUTO failed: {exc}"
                    print(f"[{datetime.now(timezone).isoformat(timespec='seconds')}] {message}")
                    _write_heartbeat(heartbeat_path, "ERROR", schedule_text, profile.code, message)
                finally:
                    service.close()
            time.sleep(max(10, args.poll_seconds))
    except KeyboardInterrupt:
        _write_heartbeat(heartbeat_path, "STOPPED", schedule_text, profile.code, "ADE Core stopped by user")
        print("ADE Core stopped")


if __name__ == "__main__":
    main()
