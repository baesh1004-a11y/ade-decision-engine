from __future__ import annotations

import argparse
import time
from datetime import datetime, time as clock_time

from recommendation.daily_service import DailyRecommendationService


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
    print("========================================")
    print(" ADE DAILY RECOMMENDATION SCHEDULER")
    print("========================================")
    print(f"Schedule : weekdays {args.hour:02d}:{args.minute:02d}")
    print(f"Poll     : every {args.poll_seconds}s")

    while True:
        now = datetime.now()
        should_run = now.weekday() < 5 and now.time() >= target_time
        if should_run:
            service = DailyRecommendationService()
            try:
                if not service.auto_completed_today():
                    print(f"[{now.isoformat(timespec='seconds')}] Starting AUTO recommendation...")
                    result = service.run(
                        "AUTO",
                        top_n=args.top,
                        weekly_pool_n=args.weekly_pool,
                        min_weekly_similarity=args.min_weekly,
                        min_sto_similarity=args.min_sto,
                    )
                    print(
                        f"[{result.finished_at}] AUTO completed: "
                        f"{result.recommendation_count} recommendations, "
                        f"{result.elapsed_seconds:.1f}s"
                    )
            except Exception as exc:
                print(f"[{datetime.now().isoformat(timespec='seconds')}] AUTO failed: {exc}")
            finally:
                service.close()
        time.sleep(max(10, args.poll_seconds))


if __name__ == "__main__":
    main()
