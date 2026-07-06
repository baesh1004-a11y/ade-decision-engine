from __future__ import annotations

import argparse
from pathlib import Path

from centerline.engine import CenterlineEngine
from datahub.repository import PriceRepository


DB_PATH = Path("datahub/market.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE centerline analysis")
    parser.add_argument("ticker")
    parser.add_argument("--market", default="kr")
    args = parser.parse_args()

    repository = PriceRepository(DB_PATH)
    try:
        data = repository.fetch_dataframe(args.market, args.ticker, source="fdr")
        snapshot = CenterlineEngine().snapshot(data)
    finally:
        repository.close()

    print("\n========================================")
    print(" ADE CENTERLINE ANALYSIS")
    print("========================================")
    print(f"Target          : {args.market.upper()}:{args.ticker}")
    print(f"Weekly CL       : {snapshot.weekly}")
    print(f"Monthly CL      : {snapshot.monthly}")
    print(f"Quarterly CL    : {snapshot.quarterly}")
    print(f"Half-Year CL    : {snapshot.half_year}")
    print(f"Yearly CL       : {snapshot.yearly}")
    print(f"Yearly Distance : {snapshot.yearly_distance_pct}%")
    print(f"Alignment       : {snapshot.alignment_score}/100")
    print(f"Slope           : {snapshot.slope_score}/100")
    print(f"Convergence     : {snapshot.convergence_score}/100")
    print(f"Breakout        : {snapshot.breakout_score}/100")
    print(f"Centerline Score: {snapshot.centerline_score}/100")
    print("\nLabels")
    for label in snapshot.labels:
        print(f"- {label}")


if __name__ == "__main__":
    main()
