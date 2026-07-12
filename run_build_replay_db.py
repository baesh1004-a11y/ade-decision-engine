from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from maintenance.job_manager import ADEJobManager
from replay.builder import ReplayEventDBBuilder
from replay.models import ADE_VERSION
from replay.repository import ReplayEventRepository
from replay.vector_builder import ReplayEventVectorBuilder


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
    parser.add_argument(
        "--skip-vectors",
        action="store_true",
        help="Skip Replay event-vector generation after the event DB update.",
    )
    args = parser.parse_args()
    full_build = bool(args.full or args.clear)

    with ADEJobManager().acquire(
        "REPLAY_DB_BUILD",
        wait=True,
        timeout_seconds=12 * 60 * 60,
    ):
        repo = ReplayEventRepository(DB_PATH)
        try:
            before_events, before_flows = repo.counts()
            before_checkpoint = repo.latest_checkpoint(ADE_VERSION, args.market)
            checkpoint_symbols = repo.checkpoint_count(ADE_VERSION, args.market)
        finally:
            repo.close()

        print("\n========================================")
        print(" ADE REPLAY EVENT DB UPDATE")
        print("========================================")
        print(f"Database           : {DB_PATH}")
        print(f"ADE Version        : {ADE_VERSION}")
        print(f"Market             : {args.market}")
        print(f"Limit              : {args.limit or 'none'}")
        print(f"Mode               : {'FULL REBUILD' if full_build else 'INCREMENTAL'}")
        print(f"Existing Events    : {before_events}")
        print(f"Existing Flows     : {before_flows}")
        print(f"Checkpoint Symbols : {checkpoint_symbols}")
        print(f"Latest Checkpoint  : {before_checkpoint or 'none'}")
        if not full_build and before_events > 0 and checkpoint_symbols == 0:
            print("Migration          : pending; existing Replay DB will be reused")

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

        vector_stats = None
        if not args.skip_vectors:
            vector_builder = ReplayEventVectorBuilder(DB_PATH)
            try:
                vector_stats = vector_builder.build(
                    ade_version=ADE_VERSION,
                    rebuild=full_build,
                )
            finally:
                vector_builder.close()

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
        print(f"Migrated Checkpoints: {stats.get('migrated_checkpoints', 0)}")
        print(f"Scanned Symbols    : {stats.get('symbols', 0)}")
        print(f"Updated Symbols    : {stats.get('updated_symbols', 0)}")
        print(f"Up-to-date Symbols : {stats.get('skipped_up_to_date', 0)}")
        print(f"No-data Symbols    : {stats.get('skipped_no_data', 0)}")
        print(f"Added Events       : {event_count}")
        print(f"Added Flows        : {flow_count}")
        print(f"Total Events       : {total_events}")
        print(f"Total Flows        : {total_flows}")
        if vector_stats is not None:
            print(f"Scanned Vectors    : {vector_stats.scanned_events}")
            print(f"Upserted Vectors   : {vector_stats.upserted_vectors}")
            print(f"Skipped Vectors    : {vector_stats.skipped_events}")
            print(f"Total Vectors      : {vector_stats.total_vectors}")
        else:
            print("Replay Vectors     : skipped")
        print(f"Checkpoint Symbols : {stats.get('checkpoint_symbols', 0)}")
        print(f"Latest Checkpoint  : {stats.get('latest_checkpoint') or 'none'}")
        print(f"Elapsed            : {elapsed:.1f}s")


if __name__ == "__main__":
    main()
