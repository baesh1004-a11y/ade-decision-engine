from __future__ import annotations

import argparse
from pathlib import Path

from replay.builder import ReplayEventDBBuilder
from replay.repository import ReplayEventRepository


DB_PATH = Path("datahub/market.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE v2 Replay Event DB Builder")
    parser.add_argument("--market", default="kr")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    print("\n========================================")
    print(" ADE v2 REPLAY EVENT DB BUILD")
    print("========================================")
    print(f"Database : {DB_PATH}")
    print(f"Market   : {args.market}")
    print(f"Limit    : {args.limit or 'none'}")
    print(f"Clear    : {args.clear}")

    builder = ReplayEventDBBuilder(DB_PATH)
    try:
        event_count, flow_count = builder.build(market=args.market, limit=args.limit, clear=args.clear)
    finally:
        builder.close()

    repo = ReplayEventRepository(DB_PATH)
    try:
        total_events, total_flows = repo.counts()
    finally:
        repo.close()

    print("\n========================================")
    print(" REPLAY DB SUMMARY")
    print("========================================")
    print(f"Built Events : {event_count}")
    print(f"Built Flows  : {flow_count}")
    print(f"Total Events : {total_events}")
    print(f"Total Flows  : {total_flows}")


if __name__ == "__main__":
    main()
