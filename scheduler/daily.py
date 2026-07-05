from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta


PIPELINE = [
    [sys.executable, "run_collect_data.py"],
    [sys.executable, "run_recommendations.py"],
]


def run_once() -> None:
    for command in PIPELINE:
        print(f"\n[Scheduler] running: {' '.join(command)}")
        subprocess.run(command, check=True)


def seconds_until(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE daily scheduler")
    parser.add_argument("--once", action="store_true", help="run the pipeline once and exit")
    parser.add_argument("--hour", type=int, default=6)
    parser.add_argument("--minute", type=int, default=0)
    args = parser.parse_args()

    if args.once:
        run_once()
        return

    while True:
        wait_seconds = seconds_until(args.hour, args.minute)
        print(f"[Scheduler] next run in {wait_seconds / 3600:.2f} hours")
        time.sleep(wait_seconds)
        try:
            run_once()
        except Exception as exc:
            print(f"[Scheduler] pipeline failed: {exc}")


if __name__ == "__main__":
    main()
