from __future__ import annotations

import argparse
import subprocess
import sys

from candidate.scanner import scan_candidates


def run(command: list[str]) -> None:
    print(f"\n$ {' '.join(command)}")
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE daily full pipeline")
    parser.add_argument("--collect", action="store_true", help="collect prices first")
    parser.add_argument("--build-cache", action="store_true", help="build vector cache")
    parser.add_argument("--min-score", type=int, default=55)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    if args.collect:
        run([sys.executable, "run_collect_data.py"])
    if args.build_cache:
        run([sys.executable, "run_build_cache.py"])

    candidates = scan_candidates(min_score=args.min_score, top_n=args.top)
    print("\n========================================")
    print(" ADE DAILY CANDIDATE -> REPLAY PIPELINE")
    print("========================================")
    print(f"Candidates: {len(candidates)}")

    for i, candidate in enumerate(candidates, start=1):
        print(f"\n[{i}/{len(candidates)}] {candidate.market.upper()}:{candidate.ticker} score={candidate.score}")
        run([
            sys.executable,
            "analyze.py",
            candidate.ticker,
            "--market",
            candidate.market,
            "--top",
            "20",
            "--min-similarity",
            "55",
        ])


if __name__ == "__main__":
    main()
