from __future__ import annotations

import argparse

from recommendation.event_recommender import RecentMoneyEventRecommender


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE v3 recent money event recommender")
    parser.add_argument("--candidate-years", type=int, default=2)
    parser.add_argument("--lookback-months", type=int, default=6)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--weekly-pool", type=int, default=100)
    parser.add_argument("--min-weekly", type=float, default=70.0)
    parser.add_argument("--min-sto", type=float, default=70.0)
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

    print("\n========================================")
    print(" ADE v3 RECENT MONEY EVENT RECOMMENDER")
    print("========================================")
    print(f"Candidate window : recent {args.candidate_years} years")
    print(f"Weekly window    : recent {args.lookback_months} months")
    print(f"Rule             : weekly similar AND current STO3 similar")
    print(f"Recommendations  : {len(recommendations)}")
    for i, item in enumerate(recommendations, start=1):
        print(
            f"{i:02d}. {item.market.upper()}:{item.ticker} {item.name or ''} "
            f"decision={item.decision} final={item.final_similarity}% "
            f"weekly={item.weekly_similarity}% sto={item.sto_similarity}% "
            f"recent_event={item.recent_event_date} money={item.recent_money_ratio}x "
            f"matched={item.matched_event_id} max_return={item.matched_max_return}% mdd={item.matched_max_drawdown}%"
        )
        for reason in item.reasons:
            print(f"    - {reason}")


if __name__ == "__main__":
    main()
