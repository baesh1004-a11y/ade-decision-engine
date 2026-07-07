from __future__ import annotations

import argparse
from pathlib import Path

from recommendation.event_recommender import RecentMoneyEventRecommender
from report.recommendation_html_report import render_recommendation_html


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE v4 recent money event recommender")
    parser.add_argument("--candidate-years", type=int, default=2)
    parser.add_argument("--lookback-months", type=int, default=6)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--weekly-pool", type=int, default=100)
    parser.add_argument("--min-weekly", type=float, default=85.0)
    parser.add_argument("--min-sto", type=float, default=85.0)
    parser.add_argument("--replay-top", type=int, default=5)
    parser.add_argument("--report", default="output/recommendation_report.html")
    args = parser.parse_args()

    engine = RecentMoneyEventRecommender()
    try:
        recommendations = engine.recommend(
            candidate_years=args.candidate_years,
            lookback_months=args.lookback_months,
            top_n=args.top,
            weekly_pool_n=args.weekly_pool,
            min_weekly_similarity=args.min_weekly,
            min_sto_similarity=args.min_sto,
            replay_top_n=args.replay_top,
        )
    finally:
        engine.close()

    report_path = render_recommendation_html(recommendations, Path(args.report), lookback_months=args.lookback_months)

    print("\n========================================")
    print(" ADE v4 RECENT MONEY EVENT RECOMMENDER")
    print("========================================")
    print(f"Candidate window : recent {args.candidate_years} years")
    print(f"Weekly window    : recent {args.lookback_months} months")
    print(f"Rule             : weekly >= {args.min_weekly:.1f}% AND STO >= {args.min_sto:.1f}%")
    print(f"Replay matches   : Top {args.replay_top} per recommendation")
    print(f"Recommendations  : {len(recommendations)}")
    print(f"HTML report      : {report_path}")
    print("\nRank | Stock | Decision | Top1 Final | Top1 Weekly | Top1 STO | Top1 Replay | Replay Max | MDD")
    print("-----|-------|----------|------------|-------------|----------|-------------|------------|-----")
    for i, item in enumerate(recommendations, start=1):
        print(
            f"{i:02d} | {item.market.upper()}:{item.ticker} {item.name or ''} | "
            f"{item.decision} | {item.final_similarity:.2f}% | "
            f"{item.weekly_similarity:.2f}% | {item.sto_similarity:.2f}% | "
            f"{item.matched_event_id} | {item.matched_max_return}% | {item.matched_max_drawdown}%"
        )
        for j, match in enumerate(getattr(item, "replay_matches", [])[: args.replay_top], start=1):
            print(
                f"    Top{j}: {match.event_id} final={match.final_similarity:.2f}% "
                f"weekly={match.weekly_similarity:.2f}% sto={match.sto_similarity:.2f}% "
                f"max={match.max_return}% mdd={match.max_drawdown}%"
            )


if __name__ == "__main__":
    main()
