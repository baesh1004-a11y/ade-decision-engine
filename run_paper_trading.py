from __future__ import annotations

import argparse

from broker.kis import kis_broker_from_env
from paper_trading.order_manager import PaperOrderManager
from paper_trading.portfolio import PaperPortfolioRepository
from recommendation.event_recommender import RecentMoneyEventRecommender


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE v5 KIS paper trading buy runner")
    parser.add_argument("--candidate-years", type=int, default=2)
    parser.add_argument("--lookback-months", type=int, default=6)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--weekly-pool", type=int, default=100)
    parser.add_argument("--min-weekly", type=float, default=85.0)
    parser.add_argument("--min-sto", type=float, default=85.0)
    parser.add_argument("--replay-top", type=int, default=5)
    parser.add_argument("--budget", type=int, default=1_000_000)
    parser.add_argument("--dry-run", action="store_true", help="Preview only. No KIS order is sent.")
    parser.add_argument("--execute", action="store_true", help="Send paper orders to KIS mock trading account.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt when --execute is used.")
    parser.add_argument(
        "--allow-rebuy",
        action="store_true",
        help="Allow another BUY for a stock that is already held. Default is to skip held stocks.",
    )
    args = parser.parse_args()

    if args.execute and args.dry_run:
        raise SystemExit("Use either --dry-run or --execute, not both.")
    dry_run = not args.execute

    recommender = RecentMoneyEventRecommender()
    order_manager = PaperOrderManager()
    portfolio = PaperPortfolioRepository()
    try:
        recommendations = recommender.recommend(
            candidate_years=args.candidate_years,
            lookback_months=args.lookback_months,
            top_n=args.top,
            weekly_pool_n=args.weekly_pool,
            min_weekly_similarity=args.min_weekly,
            min_sto_similarity=args.min_sto,
            replay_top_n=args.replay_top,
        )
        held_position_keys = portfolio.open_position_keys()
        plans = order_manager.build_buy_plans(
            recommendations,
            budget_per_stock=args.budget,
            held_position_keys=held_position_keys,
            allow_rebuy=args.allow_rebuy,
        )

        print("\n========================================")
        print(" ADE PAPER TRADING BUY PLAN")
        print("========================================")
        print(f"Mode             : {'DRY RUN / PREVIEW' if dry_run else 'KIS PAPER ORDER'}")
        print(f"Rule             : weekly >= {args.min_weekly:.1f}% AND STO >= {args.min_sto:.1f}%")
        print(f"Budget per stock : {args.budget:,} KRW")
        print(f"Recommendations  : {len(recommendations)}")
        print(f"Held positions   : {len(held_position_keys)}")
        print(f"Rebuy policy     : {'ALLOW' if args.allow_rebuy else 'SKIP HELD'}")
        print(f"Skipped held     : {len(order_manager.last_skipped_held)}")
        print(f"Order plans      : {len(plans)}")

        if order_manager.last_skipped_held:
            print("\nAlready held / skipped:")
            for key in order_manager.last_skipped_held:
                print(f"- {key.upper()}")

        print("\nRank | Stock | Qty | Ref Price | Est Amount | Final | Weekly | STO | Top1 Replay")
        print("-----|-------|-----|-----------|------------|-------|--------|-----|------------")
        total = 0
        for i, plan in enumerate(plans, start=1):
            total += plan.estimated_amount
            print(
                f"{i:02d} | {plan.market.upper()}:{plan.ticker} {plan.name or ''} | "
                f"{plan.quantity:,} | {plan.reference_price:,.0f} | {plan.estimated_amount:,} | "
                f"{(plan.final_similarity or 0):.2f}% | {(plan.weekly_similarity or 0):.2f}% | "
                f"{(plan.sto_similarity or 0):.2f}% | {plan.top1_event_id or ''}"
            )
        print(f"\nTotal estimated buy amount: {total:,} KRW")

        if not plans:
            print("No paper orders to submit. All recommendations may already be held.")
            return

        if dry_run:
            print("\nDry run only. To send mock orders, run with --execute.")
            return

        if not args.yes:
            confirm = input("\nSend these BUY orders to KIS paper account? Type YES: ").strip()
            if confirm != "YES":
                print("Cancelled.")
                return

        broker = kis_broker_from_env()
        executions = order_manager.execute(broker, plans, dry_run=False)
        saved = portfolio.save_executions(executions)

        print("\n========================================")
        print(" ADE PAPER ORDER RESULTS")
        print("========================================")
        for i, execution in enumerate(executions, start=1):
            status = "ACCEPTED" if execution.accepted else "REJECTED"
            print(
                f"{i:02d} | {status} | {execution.plan.market.upper()}:{execution.plan.ticker} "
                f"qty={execution.plan.quantity} order_id={execution.order_id} msg={execution.message}"
            )
        print(f"Saved executions : {saved}")
    finally:
        recommender.close()
        order_manager.close()
        portfolio.close()


if __name__ == "__main__":
    main()
