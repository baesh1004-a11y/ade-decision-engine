from __future__ import annotations

import argparse
from pathlib import Path

from recommendation.event_recommender import RecentMoneyEventRecommender
from report.recommendation_html_report import render_recommendation_html


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE v3 recent money event recommender")
    parser.add_argument("--candidate-years", type=int, default=2)
    parser.add_argument("--lookback-months", type=int, default=6)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--weekly-pool", type=int, default=100)
    parser.add_argument("--min-weekly", type=float, default=70.0)
    parser.add_argument("--min-sto", type=float, default=70.0)
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
        )
    finally:
        engine.close()

    report_path = render_recommendation_html(recommendations, Path(args.report))

    print("\n========================================")
    print(" ADE v3 RECENT MONEY EVENT RECOMMENDER")
    print("========================================")
    print(f"Candidate window : recent {args.candidate_years} years")
    print(f"Weekly window    : recent {args.lookback_months} months")
    print(f"Rule             : weekly shape AND current STO3 structure")
    print(f"Recommendations  : {len(recommendations)}")
    print(f"HTML report      : {report_path}")
    print("\nRank | Stock | Decision | Final | Weekly | STO | Replay Max | MDD | Recent Event")
    print("-----|-------|----------|-------|--------|-----|------------|-----|-------------")
    for i, item in enumerate(recommendations, start=1):
        print(
            f"{i:02d} | {item.market.upper()}:{item.ticker} {item.name or ''} | "
            f"{item.decision} | {item.final_similarity:.2f}% | "
            f"{item.weekly_similarity:.2f}% | {item.sto_similarity:.2f}% | "
            f"{item.matched_max_return}% | {item.matched_max_drawdown}% | {item.recent_event_date}"
        )


if __name__ == "__main__":
    main()
