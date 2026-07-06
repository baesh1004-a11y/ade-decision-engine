from __future__ import annotations

import argparse

from candidate.scanner import scan_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE candidate scanner")
    parser.add_argument("--min-score", type=int, default=55)
    parser.add_argument("--top", type=int, default=50)
    args = parser.parse_args()

    candidates = scan_candidates(min_score=args.min_score, top_n=args.top)
    print("\n========================================")
    print(" ADE CANDIDATE SCANNER")
    print("========================================")
    print(f"Candidates: {len(candidates)}")
    for i, item in enumerate(candidates, start=1):
        print(
            f"{i:02d}. {item.market.upper()}:{item.ticker} {item.name or ''} "
            f"score={item.score} action={item.action} "
            f"vol20x={item.volume_ratio_20d} vol120x={item.volume_ratio_120d} state={item.state_score}"
        )
        for reason in item.reasons[:5]:
            print(f"    - {reason}")


if __name__ == "__main__":
    main()
