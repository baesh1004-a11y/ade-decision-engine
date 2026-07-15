from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

from maintenance.job_manager import ADEJobManager
from replay.builder import ReplayEventDBBuilder
from replay.models import ADE_VERSION
from replay.repository import ReplayEventRepository
from replay.vector_builder import ReplayEventVectorBuilder


DB_PATH = Path("datahub/us_market.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE US Replay Event DB Builder")
    parser.add_argument("--limit", type=int, default=0, help="테스트용 종목 수 제한. 0이면 전체")
    parser.add_argument("--full", action="store_true", help="미국 Replay 이벤트·흐름·체크포인트를 전부 재구축")
    parser.add_argument("--clear", action="store_true", help="--full 호환 별칭")
    parser.add_argument("--skip-vectors", action="store_true", help="Replay 벡터 생성을 생략")
    args = parser.parse_args()
    full_build = bool(args.full or args.clear)

    if not DB_PATH.exists():
        raise SystemExit("datahub/us_market.db가 없습니다. 먼저 python run_build_us_market_db.py 를 실행하세요.")

    with ADEJobManager(
        lock_path="output/us_replay_job.lock",
        status_path="output/us_replay_job_status.json",
    ).acquire("US_REPLAY_DB_BUILD", wait=True, timeout_seconds=24 * 60 * 60):
        repo = ReplayEventRepository(DB_PATH)
        try:
            before_events, before_flows = repo.counts()
            checkpoint_symbols = repo.checkpoint_count(ADE_VERSION, "us")
            latest_checkpoint = repo.latest_checkpoint(ADE_VERSION, "us")
        finally:
            repo.close()

        print("\n========================================")
        print(" ADE US REPLAY EVENT DB UPDATE")
        print("========================================")
        print(f"Database           : {DB_PATH}")
        print(f"ADE Version        : {ADE_VERSION}")
        print("Market             : us")
        print("Price Source       : yfinance")
        print(f"Limit              : {args.limit or 'none'}")
        print(f"Mode               : {'FULL REBUILD' if full_build else 'INCREMENTAL'}")
        print(f"Existing Events    : {before_events}")
        print(f"Existing Flows     : {before_flows}")
        print(f"Checkpoint Symbols : {checkpoint_symbols}")
        print(f"Latest Checkpoint  : {latest_checkpoint or 'none'}")

        started = perf_counter()
        builder = ReplayEventDBBuilder(DB_PATH, price_source="yfinance")
        try:
            event_count, flow_count = builder.build(
                market="us",
                limit=int(args.limit),
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

        repo = ReplayEventRepository(DB_PATH)
        try:
            total_events, total_flows = repo.counts()
        finally:
            repo.close()

        elapsed = perf_counter() - started
        print("\n========================================")
        print(" US REPLAY DB UPDATE SUMMARY")
        print("========================================")
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
