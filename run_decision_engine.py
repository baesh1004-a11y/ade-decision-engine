from __future__ import annotations

import argparse
from pathlib import Path

from datahub.repository import PriceRepository
from decision.engine import ReplayDecisionEngine


DB_PATH = Path("datahub/market.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE v2 Replay Decision Engine")
    parser.add_argument("ticker")
    parser.add_argument("--market", default="kr")
    parser.add_argument("--name", default=None)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--environment-score", type=int, default=70)
    args = parser.parse_args()

    repository = PriceRepository(DB_PATH)
    try:
        result = ReplayDecisionEngine(repository, environment_score=args.environment_score).decide(
            args.market,
            args.ticker,
            name=args.name,
            top_n=args.top,
        )
    finally:
        repository.close()

    print("\n========================================")
    print(" ADE v2 REPLAY DECISION ENGINE")
    print("========================================")
    print(f"Target        : {args.market.upper()}:{args.ticker}")
    print(f"Decision      : {result.decision}")
    print(f"Replay Score  : {result.replay_score}/100")
    print(f"Environment   : {result.environment_score}/100")
    print(f"Reproduction  : {result.reproduction_score}/100")
    print(f"Current State : {result.current_state.state_key}")
    if result.event:
        print(f"Money Event   : {result.event.event_date} / {result.event.money_ratio_120d}x")
    else:
        print("Money Event   : NONE - WAIT")
    print("\nDecision Reasons")
    for reason in result.decision_reason:
        print(f"- {reason}")
    print("\nReplay Flow Cases")
    for i, case in enumerate(result.cases[:args.top], start=1):
        print(
            f"{i:02d}. {case.market.upper()}:{case.ticker} {case.name or ''} "
            f"event={case.event.event_date} money={case.event.money_ratio_120d}x "
            f"sim={case.state_similarity}% 10w={case.flow_return_10w}% "
            f"20w={case.flow_return_20w}% max30w={case.max_return_30w}% mdd30w={case.max_drawdown_30w}%"
        )


if __name__ == "__main__":
    main()
