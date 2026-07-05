from __future__ import annotations

from pathlib import Path

from backtest.engine import run_backtest, summarize_backtest
from datahub.repository import PriceRepository
from universe.manager import DynamicUniverseManager


DB_PATH = Path("datahub/market.db")


def main() -> None:
    repository = PriceRepository(DB_PATH)
    try:
        print("\n==============================")
        print("       ADE BACKTEST v1")
        print("==============================")
        for symbol in DynamicUniverseManager().active():
            data = repository.fetch_dataframe(symbol.market, symbol.ticker, source="fdr")
            if len(data) < 300:
                print(f"{symbol.market.upper()}:{symbol.ticker} skipped (need 300+ rows, have {len(data)})")
                continue
            result = run_backtest(data, min_score=70)
            summary = summarize_backtest(result, primary_horizon=20)
            print(
                f"{symbol.market.upper()}:{symbol.ticker} "
                f"signals={summary['signals']} "
                f"win_rate={summary['win_rate']} "
                f"avg_return={summary['avg_return']} "
                f"avg_mdd={summary['avg_mdd']}"
            )
    finally:
        repository.close()


if __name__ == "__main__":
    main()
