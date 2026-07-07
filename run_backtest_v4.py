from __future__ import annotations

import argparse
import csv
from pathlib import Path

from backtest.walk_forward import WalkForwardBacktester
from report.backtest_html_report import render_backtest_html


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE v4 walk-forward backtest")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--market", default="kr")
    parser.add_argument("--lookback-months", type=int, default=6)
    parser.add_argument("--hold-days", type=int, default=126)
    parser.add_argument("--min-weekly", type=float, default=85.0)
    parser.add_argument("--min-sto", type=float, default=85.0)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--event-limit", type=int, default=0)
    parser.add_argument("--weekly-pool", type=int, default=80)
    parser.add_argument("--report", default="output/backtest_report.html")
    parser.add_argument("--csv", default="output/backtest_trades.csv")
    args = parser.parse_args()

    backtester = WalkForwardBacktester()
    try:
        trades = backtester.run(
            start=args.start,
            end=args.end,
            market=args.market,
            lookback_months=args.lookback_months,
            hold_days=args.hold_days,
            min_weekly_similarity=args.min_weekly,
            min_sto_similarity=args.min_sto,
            top_n=args.top,
            event_limit=args.event_limit,
            weekly_pool_n=args.weekly_pool,
        )
        summary = backtester.summarize(trades)
    finally:
        backtester.close()

    csv_path = Path(args.csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(trades[0].to_dict().keys()) if trades else ["empty"])
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade.to_dict())

    report_path = render_backtest_html(summary, trades, args.report)

    print("\n========================================")
    print(" ADE v4 WALK-FORWARD BACKTEST")
    print("========================================")
    print(f"Period           : {args.start} ~ {args.end}")
    print(f"Market           : {args.market}")
    print(f"Rule             : weekly >= {args.min_weekly:.1f}% AND STO >= {args.min_sto:.1f}%")
    print(f"Hold days        : {args.hold_days}")
    print(f"Trades           : {summary.trades}")
    print(f"Win rate         : {summary.win_rate:.2f}%")
    print(f"Avg return       : {summary.avg_return:.2f}%")
    print(f"Median return    : {summary.median_return:.2f}%")
    print(f"Avg max return   : {summary.avg_max_return:.2f}%")
    print(f"Avg MDD          : {summary.avg_max_drawdown:.2f}%")
    print(f"Best/Worst       : {summary.best_return:.2f}% / {summary.worst_return:.2f}%")
    print(f"CSV              : {csv_path}")
    print(f"HTML report      : {report_path}")


if __name__ == "__main__":
    main()
