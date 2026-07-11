from __future__ import annotations

import argparse
import json

from feedback.engine import FeedbackEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Update ADE feedback performance for all open cases")
    parser.add_argument("--db", default="datahub/market.db")
    args = parser.parse_args()

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
