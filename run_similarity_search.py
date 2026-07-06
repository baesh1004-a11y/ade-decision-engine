from __future__ import annotations

import argparse

from similarity.ade_similarity import ADESimilarityEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE v2 weekly + STO AND similarity search")
    parser.add_argument("ticker")
    parser.add_argument("--market", default="kr")
    parser.add_argument("--weekly-top", type=int, default=100)
    parser.add_argument("--sto-top", type=int, default=20)
    args = parser.parse_args()

    engine = ADESimilarityEngine()
    try:
        candidates = engine.search(args.market, args.ticker, weekly_top_n=args.weekly_top, sto_top_n=args.sto_top)
    finally:
        engine.close()

    print("\n========================================")
    print(" ADE v2 SIMILARITY SEARCH")
    print("========================================")
    print(f"Target      : {args.market.upper()}:{args.ticker}")
    print(f"Candidates  : {len(candidates)}")
    print("Rule        : Weekly similarity first, then STO 3-layer similarity")
    for i, c in enumerate(candidates, start=1):
        print(
            f"{i:02d}. {c.event_id} "
            f"weekly={c.weekly_similarity}% sto={c.sto_similarity}% final={c.final_similarity}% "
            f"weekly_pattern={c.weekly_pattern} sto={c.sto_structure}"
        )


if __name__ == "__main__":
    main()
