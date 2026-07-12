from __future__ import annotations

import argparse

from replay.models import ADE_VERSION
from replay.vector_builder import ReplayEventVectorBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Replay event vectors")
    parser.add_argument("--db", default="datahub/market.db")
    parser.add_argument("--all-versions", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    builder = ReplayEventVectorBuilder(args.db)
    try:
        stats = builder.build(
            ade_version=None if args.all_versions else ADE_VERSION,
            rebuild=args.rebuild,
        )
    finally:
        builder.close()

    print("\n========================================")
    print(" REPLAY EVENT VECTOR BUILD SUMMARY")
    print("========================================")
    print(f"ADE Version       : {'all' if args.all_versions else ADE_VERSION}")
    print(f"Scanned Events    : {stats.scanned_events}")
    print(f"Upserted Vectors  : {stats.upserted_vectors}")
    print(f"Skipped Events    : {stats.skipped_events}")
    print(f"Total Vectors     : {stats.total_vectors}")


if __name__ == "__main__":
    main()
