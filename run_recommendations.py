from __future__ import annotations

from pathlib import Path

from datahub.repository import PriceRepository
from features.engine import FeatureEngine
from portfolio.engine import PortfolioEngine
from recommendation.engine import RecommendationEngine
from recommendation.models import RecommendationInput
from universe.manager import DynamicUniverseManager


DB_PATH = Path("datahub/market.db")


def build_universe(repository: PriceRepository) -> list[RecommendationInput]:
    feature_engine = FeatureEngine()
    inputs: list[RecommendationInput] = []

    for symbol in DynamicUniverseManager().active():
        data = repository.fetch_dataframe(symbol.market, symbol.ticker, source="fdr")
        if len(data) < 30:
            continue
        inputs.append(
            RecommendationInput(
                market=symbol.market,
                ticker=symbol.ticker,
                name=symbol.name,
                market_data=feature_engine.transform(data),
                sector=symbol.sector,
            )
        )
    return inputs


def print_report() -> None:
    repository = PriceRepository(DB_PATH)
    try:
        universe = build_universe(repository)
        report = RecommendationEngine().rank(universe, top_n=5)
        portfolio = PortfolioEngine().allocate(report.recommendations, max_positions=5)

        print("\n==============================")
        print("      ADE DAILY PICKS v3")
        print("==============================")
        print("Source  : SQLite DataHub")
        print(f"Database: {DB_PATH}")
        print(f"Universe: {report.total_universe} symbols")
        print(f"Selected: Top {report.selected_count}\n")

        for rank, item in enumerate(report.recommendations, start=1):
            stars = "★" * max(1, min(5, item.final_score // 20))
            print(f"{rank}. {item.ticker} | {item.name or ''}")
            print(f"   Market     : {item.market.upper()}")
            print(f"   Sector     : {item.sector or '-'}")
            print(f"   Score      : {item.final_score} / 100")
            print(f"   Grade      : {item.grade} {stars}")
            print(f"   Action     : {item.action}")
            print(f"   Confidence : {item.confidence:.2f}")
            print("   Reasons")
            for reason in item.reasons[:5]:
                print(f"    - {reason}")
            if item.risk_flags:
                print("   Risk Flags")
                for flag in item.risk_flags:
                    print(f"    - {flag}")
            print("------------------------------")

        print("\nPORTFOLIO")
        if not portfolio:
            print("No eligible positions")
        for position in portfolio:
            print(
                f"- {position.market.upper()}:{position.ticker} "
                f"weight={position.weight:.1%} score={position.score} action={position.action}"
            )
    finally:
        repository.close()


if __name__ == "__main__":
    print_report()
