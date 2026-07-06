from __future__ import annotations

import argparse
from pathlib import Path

from datahub.repository import PriceRepository
from pattern.cross_universe_replay import CrossUniverseReplayEngine


DB_PATH = Path("datahub/market.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE cross-universe replay search")
    parser.add_argument("--market", default="kr")
    parser.add_argument("--ticker", default="005930")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-similarity", type=float, default=55.0)
    args = parser.parse_args()

    repository = PriceRepository(DB_PATH)
    try:
        result = CrossUniverseReplayEngine(repository).search(
            args.market,
            args.ticker,
            top_n=args.top,
            min_similarity=args.min_similarity,
        )
    finally:
        repository.close()

    print("\n========================================")
    print(" ADE CROSS-UNIVERSE REPLAY SEARCH")
    print("========================================")
    print(f"Target       : {result.target_market.upper()}:{result.target_ticker}")
    print(f"State Score  : {result.current_state.state_score}/100")
    print(f"Replay Prob. : {result.replay_probability}% ({result.grade})")
    print(f"Action       : {result.action}")
    print(f"Cases        : {len(result.cases)}")
    print(f"Avg 20D Ret. : {result.avg_return_20d}")
    print(f"Avg 60D Ret. : {result.avg_return_60d}")
    print(f"Win Rate 20D : {result.win_rate_20d}")
    print(f"Avg MDD 20D  : {result.avg_drawdown_20d}")
    print("\nCurrent State Labels")
    for label in result.current_state.labels:
        print(f"- {label}")

    print("\nTop Similar Replay Cases")
    for index, case in enumerate(result.cases, start=1):
        print(
            f"{index:02d}. {case.market.upper()}:{case.ticker} {case.name or ''} "
            f"{case.start_date}~{case.end_date} "
            f"sim={case.similarity}% "
            f"20D={case.forward_return_20d}% "
            f"60D={case.forward_return_60d}% "
            f"MDD20={case.drawdown_20d}%"
        )


if __name__ == "__main__":
    main()
