from __future__ import annotations

from pathlib import Path

import pandas as pd

from datahub.repository import PriceRepository
from recommendation.engine import RecommendationEngine
from recommendation.models import RecommendationInput


DB_PATH = Path("datahub/market.db")

SYMBOL_META = {
    ("us", "NVDA"): ("NVIDIA", "Semiconductor"),
    ("us", "MSFT"): ("Microsoft", "Software"),
    ("us", "AAPL"): ("Apple", "Hardware"),
    ("kr", "005930"): ("Samsung Electronics", "Semiconductor"),
    ("kr", "000660"): ("SK Hynix", "Semiconductor"),
}


def make_market_data(rows: int = 140, start: float = 100.0, step: float = 0.5, volume_boost: float = 2.0) -> pd.DataFrame:
    records = []
    for i in range(rows):
        close = start + i * step
        volume = 1_000_000
        if i == rows - 1:
            volume = int(volume * volume_boost)
        records.append({"Close": close, "Volume": volume})
    return pd.DataFrame(records)


def build_sample_universe() -> list[RecommendationInput]:
    return [
        RecommendationInput("us", "NVDA", "NVIDIA", make_market_data(step=0.8, volume_boost=2.5), "Semiconductor"),
        RecommendationInput("kr", "000660", "SK Hynix", make_market_data(step=0.65, volume_boost=2.2), "Semiconductor"),
        RecommendationInput("us", "MSFT", "Microsoft", make_market_data(step=0.5, volume_boost=1.8), "Software"),
        RecommendationInput("kr", "005930", "Samsung Electronics", make_market_data(step=0.4, volume_boost=1.6), "Semiconductor"),
        RecommendationInput("us", "AAPL", "Apple", make_market_data(step=0.25, volume_boost=1.2), "Hardware"),
        RecommendationInput("us", "TSLA", "Tesla", make_market_data(step=-0.1, volume_boost=0.7), "EV"),
    ]


def build_datahub_universe() -> list[RecommendationInput]:
    if not DB_PATH.exists():
        return []

    repository = PriceRepository(DB_PATH)
    try:
        universe: list[RecommendationInput] = []
        for (market, ticker), (name, sector) in SYMBOL_META.items():
            data = repository.fetch_dataframe(market=market, ticker=ticker, source="fdr")
            if len(data) >= 30:
                universe.append(
                    RecommendationInput(
                        market=market,
                        ticker=ticker,
                        name=name,
                        market_data=data,
                        sector=sector,
                    )
                )
        return universe
    finally:
        repository.close()


def print_report() -> None:
    universe = build_datahub_universe()
    source_label = "SQLite DataHub"
    if not universe:
        universe = build_sample_universe()
        source_label = "sample data"

    report = RecommendationEngine().rank(universe, top_n=5)

    print("\n==============================")
    print("      ADE DAILY PICKS v2")
    print("==============================")
    print(f"Source  : {source_label}")
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


if __name__ == "__main__":
    print_report()
