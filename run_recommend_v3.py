from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from time import perf_counter

from recommendation.event_recommender import RecentMoneyEventRecommender
from report.recommendation_html_report import render_recommendation_html


DB_PATH = Path("datahub/market.db")


def _db_count(table: str) -> int:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE Replay prediction recommender")
    parser.add_argument("--candidate-years", type=int, default=2)
    parser.add_argument("--lookback-months", type=int, default=6)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--weekly-pool", type=int, default=100)
    parser.add_argument("--min-weekly", type=float, default=85.0)
    parser.add_argument("--min-sto", type=float, default=85.0)
    parser.add_argument("--replay-top", type=int, default=5)
    parser.add_argument("--report", default="output/recommendation_report.html")
    args = parser.parse_args()

    event_count = _db_count("replay_events")
    vector_count = _db_count("replay_event_vectors")
    flow_count = _db_count("replay_event_flow")

    print("\n========================================")
    print(" ADE REPLAY RECOMMENDATION START")
    print("========================================")
    print(f"Database         : {DB_PATH}")
    print(f"Replay Events    : {event_count:,}")
    print(f"Replay Vectors   : {vector_count:,}")
    print(f"Replay Flows     : {flow_count:,}")
    print(f"Vector Prefilter : {'ENABLED' if vector_count > 0 else 'DISABLED'}")
    print(f"Candidate Window : recent {args.candidate_years} years")
    print(f"Lookback Window  : {args.lookback_months} months")
    print(f"Threshold        : weekly {args.min_weekly:.1f}% / STO {args.min_sto:.1f}%")
    print("\n[1/3] Loading recent candidates and Replay vector index...")

    started = perf_counter()
    engine = RecentMoneyEventRecommender(DB_PATH)
    try:
        print("[2/3] Running vector prefilter, weekly/STO matching and prediction...")
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

    print("[3/3] Writing HTML recommendation report...")
    report_path = render_recommendation_html(recommendations, Path(args.report), lookback_months=args.lookback_months)
    elapsed = perf_counter() - started

    print("\n========================================")
    print(" ADE REPLAY PREDICTION RECOMMENDER")
    print("========================================")
    print(f"Candidate window : recent {args.candidate_years} years")
    print(f"Weekly window    : recent {args.lookback_months} months")
    print(f"Rule             : weekly >= {args.min_weekly:.1f}% AND STO >= {args.min_sto:.1f}%")
    print(f"Replay matches   : Top {args.replay_top} per recommendation")
    print(f"Vector prefilter : {'enabled' if vector_count > 0 else 'disabled'}")
    print(f"Recommendations  : {len(recommendations)}")
    print(f"Elapsed          : {elapsed:.1f}s")
    print(f"HTML report      : {report_path}")
    print("\nRank | Stock | Decision | Grade | 7D Up | 7D Exp | 7D Max | Peak Day | Target | Stop | Final")
    print("-----|-------|----------|-------|-------|--------|--------|----------|--------|------|------")
    for i, item in enumerate(recommendations, start=1):
        p = item.prediction
        if p is None:
            prediction_text = "- | - | - | - | - | - | -"
        else:
            prediction_text = (
                f"{p.grade} | {p.seven_day_up_probability:.1f}% | {p.seven_day_expected_return:+.2f}% | "
                f"{p.expected_max_return_7d:+.2f}% | {p.expected_peak_day:.1f} | "
                f"{p.target_return:+.2f}% | {p.stop_return:.2f}%"
            )
        print(
            f"{i:02d} | {item.market.upper()}:{item.ticker} {item.name or ''} | "
            f"{item.decision} | {prediction_text} | {item.final_similarity:.2f}%"
        )
        vector_reason = next((reason for reason in item.reasons if "Replay Vector" in reason), None)
        if vector_reason:
            print(f"    Vector: {vector_reason}")
        if p is not None:
            horizon_text = ", ".join(
                f"{h.days}D up={h.up_probability:.1f}% exp={h.expected_return:+.2f}% med={h.median_return:+.2f}%"
                for h in p.horizons
            )
            print(f"    Forecast: {horizon_text}")
        for j, match in enumerate(item.replay_matches[: args.replay_top], start=1):
            print(
                f"    Top{j}: {match.event_id} final={match.final_similarity:.2f}% "
                f"weekly={match.weekly_similarity:.2f}% sto={match.sto_similarity:.2f}% "
                f"future_start_week={match.future_start_week_index}"
            )


if __name__ == "__main__":
    main()
