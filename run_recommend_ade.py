from __future__ import annotations

import argparse

from recommendation.ade_engine import ADERecommendationEngine
from report.ade_recommendation_report import ADERecommendationReportWriter


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE full recommendation runner")
    parser.add_argument("--candidate-min-score", type=int, default=55)
    parser.add_argument("--candidate-top", type=int, default=30)
    parser.add_argument("--final-top", type=int, default=10)
    parser.add_argument("--replay-top", type=int, default=20)
    parser.add_argument("--min-similarity", type=float, default=55.0)
    parser.add_argument("--no-reports", action="store_true")
    args = parser.parse_args()

    recommendations = ADERecommendationEngine().recommend(
        candidate_min_score=args.candidate_min_score,
        candidate_top_n=args.candidate_top,
        final_top_n=args.final_top,
        replay_top_n=args.replay_top,
        min_similarity=args.min_similarity,
        generate_reports=not args.no_reports,
    )
    summary_path = ADERecommendationReportWriter().write(recommendations)

    print("\n========================================")
    print(" ADE FULL RECOMMENDATION")
    print("========================================")
    print(f"Recommendations: {len(recommendations)}")
    print(f"Summary Report : {summary_path}")
    for item in recommendations:
        c = item.candidate
        r = item.replay
        print(
            f"{item.rank:02d}. {c.market.upper()}:{c.ticker} {c.name or ''} "
            f"final={item.final_score} grade={item.grade} action={item.action} "
            f"candidate={c.score} replay={r.replay_probability}% "
            f"20D={r.avg_return_20d}% win={r.win_rate_20d}%"
        )
        if item.report_path:
            print(f"    report: {item.report_path}")
        for reason in item.reasons[:5]:
            print(f"    - {reason}")


if __name__ == "__main__":
    main()
