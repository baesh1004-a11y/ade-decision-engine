from __future__ import annotations

import argparse
from pathlib import Path

from cache.vector_cache import VectorBuilder
from datahub.repository import PriceRepository
from environment.engine import EnvironmentEngine, EnvironmentSnapshot
from pattern.cross_universe_replay import CrossUniverseReplayEngine
from search.vector_index import VectorIndex


DB_PATH = Path("datahub/market.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE manual analysis command")
    parser.add_argument("ticker")
    parser.add_argument("--market", default="kr")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-similarity", type=float, default=55.0)
    parser.add_argument("--vix", type=float, default=None)
    parser.add_argument("--dxy", type=float, default=None)
    parser.add_argument("--rate", type=float, default=None)
    args = parser.parse_args()

    env_score = EnvironmentEngine().score(EnvironmentSnapshot(vix=args.vix, dxy=args.dxy, rate=args.rate))
    repository = PriceRepository(DB_PATH)
    try:
        data = repository.fetch_dataframe(args.market, args.ticker, source="fdr")
        vector_records = VectorBuilder().build_for_dataframe(args.market, args.ticker, data)
        vector_matches = []
        if vector_records:
            vector_matches = VectorIndex.from_cache(str(DB_PATH)).search(vector_records[-1].vector, top_n=10)

        replay = CrossUniverseReplayEngine(repository).search(
            args.market,
            args.ticker,
            top_n=args.top,
            min_similarity=args.min_similarity,
        )
    finally:
        repository.close()

    print("\n========================================")
    print(" ADE MANUAL ANALYSIS")
    print("========================================")
    print(f"Target       : {args.market.upper()}:{args.ticker}")
    print(f"Environment : {env_score}/100")
    print(f"State Score  : {replay.current_state.state_score}/100")
    print(f"Replay Prob. : {replay.replay_probability}% ({replay.grade})")
    print(f"Action       : {replay.action}")
    print(f"Cases        : {len(replay.cases)}")
    print(f"Avg 20D Ret. : {replay.avg_return_20d}")
    print(f"Avg 60D Ret. : {replay.avg_return_60d}")
    print(f"Win Rate 20D : {replay.win_rate_20d}")
    print(f"Avg MDD 20D  : {replay.avg_drawdown_20d}")

    print("\nCurrent State Labels")
    for label in replay.current_state.labels:
        print(f"- {label}")

    print("\nVector Top Matches")
    for index, match in enumerate(vector_matches[:10], start=1):
        print(f"{index:02d}. {match.market.upper()}:{match.ticker} {match.trade_date} vector_sim={match.similarity}%")

    print("\nReplay Top Cases")
    for index, case in enumerate(replay.cases[:10], start=1):
        print(
            f"{index:02d}. {case.market.upper()}:{case.ticker} {case.name or ''} "
            f"{case.start_date}~{case.end_date} "
            f"sim={case.similarity}% state={case.state_similarity}% shape={case.shape_similarity}% "
            f"20D={case.forward_return_20d}% 60D={case.forward_return_60d}% MDD20={case.drawdown_20d}%"
        )


if __name__ == "__main__":
    main()
