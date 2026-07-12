from __future__ import annotations

import argparse
import json

from feedback.engine import FeedbackEngine
from maintenance.job_manager import ADEJobManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Update ADE feedback performance for all open cases")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()

    with ADEJobManager().acquire(
        "FEEDBACK_UPDATE",
        wait=True,
        timeout_seconds=2 * 60 * 60,
    ):
        engine = FeedbackEngine(args.db)
        try:
            result = engine.update_open_cases()
            summary = engine.summary()
        finally:
            engine.close()

    print(json.dumps({
        "update": result,
        "summary": summary.to_dict(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
