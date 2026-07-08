from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from replay.builder import ReplayEventDBBuilder
from replay.repository import ReplayEventRepository


DB_PATH = Path("datahub/market.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE Replay Event DB Builder")
    parser.add_argument("--market", default="kr")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--full",
        action="store_true",
        help="Clear the current ADE-version Replay DB and rebuild all events.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Backward-compatible alias of --full.",
    )
    args = parser.parse_args()
    full_build = bool(args.full or args.clear)

    repo = ReplayEventRepository(DB_PATH)
    try:
        before_events, before_flows = repo.counts()
        before_checkpoint = repo.latest_checkpoint("2.0", args.market)
        checkpoint_symbols = repo.checkpoint_count("2.0", args.market)
    finally:
        repo.close()

    print("\n========================================")
    print(" ADE REPLAY EVENT DB UPDATE")
    print("========================================")
    print(f"Database           : {DB_PATH}")
    print(f"Market             : {args.market}")
    print(f"Limit              : {args.limit or 'none'}")
    print(f"Mode               : {'FULL REBUILD' if full_build else 'INCREMENTAL'}")
    print(f"Existing Events    : {before_events}")
    print(f"Existing Flows     : {before_flows}")
    print(f"Checkpoint Symbols : {checkpoint_symbols}")
    print(f"Latest Checkpoint  : {before_checkpoint or 'none'}")

    started = perf_counter()
    builder = ReplayEventDBBuilder(DB_PATH)
    try:
        event_count, flow_count = builder.build(
            market=args.market,
            limit=args.limit,
            clear=full_build,
        )
        stats = dict(builder.last_stats)
    finally:
        builder.close()
    elapsed = perf_counter() - started

    repo = ReplayEventRepository(DB_PATH)
    try:
        total_events, total_flows = repo.counts()
    finally:
        repo.close()

    print("\n========================================")
    print(" REPLAY DB UPDATE SUMMARY")
    print("========================================")
    print(f"Mode               : {'FULL REBUILD' if full_build else 'INCREMENTAL'}")
    print(f"Scanned Symbols    : {stats.get('symbols', 0)}")
    print(f"Updated Symbols    : {stats.get('updated_symbols', 0)}")
    print(f"Up-to-date Symbols : {stats.get('skipped_up_to_date', 0)}")
    print(f"No-data Symbols    : {stats.get('skipped_no_data', 0)}")
    print(f"Added Events       : {event_count}")
    print(f"Added Flows        : {flow_count}")
    print(f"Total Events       : {total_events}")
    print(f"Total Flows        : {total_flows}")
    print(f"Checkpoint Symbols : {stats.get('checkpoint_symbols', 0)}")
    print(f"Latest Checkpoint  : {stats.get('latest_checkpoint') or 'none'}")
    print(f"Elapsed            : {elapsed:.1f}s")


if __name__ == "__main__":
    main()
