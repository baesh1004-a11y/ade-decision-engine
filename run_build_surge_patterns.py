from __future__ import annotations

import argparse
from time import perf_counter

from markets.profiles import get_market_profile
from surge.pattern_engine import SurgePatternBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build 120-day patterns immediately before 5-day 30% surges")
    parser.add_argument("--market", choices=["kr", "us"], default="kr")
    parser.add_argument("--full", action="store_true", help="해당 시장 급등직전 패턴을 전부 재구축")
    parser.add_argument("--limit", type=int, default=0, help="테스트용 원본 거래대금 이벤트 수 제한")
    parser.add_argument("--money-ratio", type=float, default=10.0, help="관찰 시작 거래대금 배수")
    parser.add_argument("--observation-days", type=int, default=500, help="거래대금 이벤트 이후 추적 거래일")
    parser.add_argument("--surge-return", type=float, default=30.0, help="5거래일 최고상승률 기준")
    args = parser.parse_args()

    profile = get_market_profile(args.market)
    if not profile.db_path.exists():
        raise SystemExit(f"{profile.db_path}가 없습니다. 가격 DB와 Replay DB를 먼저 구축하세요.")

    print("\n========================================")
    print(" ADE PRE-SURGE 120D PATTERN BUILD")
    print("========================================")
    print(f"Market             : {profile.code}")
    print(f"Database           : {profile.db_path}")
    print(f"Price source       : {profile.price_source}")
    print(f"Money anchor       : {args.money_ratio:g}x")
    print(f"Observation        : {args.observation_days} sessions")
    print(f"Surge definition   : next 5 sessions +{args.surge_return:g}%")
    print("Pattern window     : 120 sessions immediately before surge")
    print(f"Mode               : {'FULL REBUILD' if args.full else 'UPSERT'}")

    started = perf_counter()
    builder = SurgePatternBuilder(
        profile.db_path,
        price_source=profile.price_source,
        source_money_ratio=float(args.money_ratio),
        observation_days=int(args.observation_days),
        surge_return=float(args.surge_return),
    )
    try:
        stats = builder.build(
            market=profile.code,
            clear=bool(args.full),
            limit=max(0, int(args.limit)),
        )
    finally:
        builder.close()

    print("\n========================================")
    print(" BUILD SUMMARY")
    print("========================================")
    print(f"Source money events : {stats.source_events}")
    print(f"Surge patterns      : {stats.patterns}")
    print(f"Pattern bars        : {stats.pattern_bars}")
    print(f"Elapsed             : {perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
