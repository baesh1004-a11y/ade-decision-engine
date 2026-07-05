from __future__ import annotations

from pathlib import Path

import pandas as pd

from collector.base import CollectorRequest
from collector.fdr import FDRCollector
from datahub.models import PriceBar
from datahub.repository import PriceRepository


DEFAULT_SYMBOLS = [
    ("us", "NVDA"),
    ("us", "MSFT"),
    ("us", "AAPL"),
    ("kr", "005930"),
    ("kr", "000660"),
]

DB_PATH = Path("datahub/market.db")


def _to_price_bars(market: str, ticker: str, source: str, data: pd.DataFrame) -> list[PriceBar]:
    records: list[PriceBar] = []
    for row in data.itertuples(index=False):
        trade_date = pd.Timestamp(row.Date).date().isoformat()
        records.append(
            PriceBar(
                market=market,
                ticker=ticker,
                trade_date=trade_date,
                open=float(row.Open),
                high=float(row.High),
                low=float(row.Low),
                close=float(row.Close),
                volume=float(row.Volume),
                adjusted_close=None,
                source=source,
            )
        )
    return records


def main() -> None:
    collector = FDRCollector()
    repository = PriceRepository(DB_PATH)

    print("\n==============================")
    print("     ADE DATA COLLECTION v2")
    print("==============================")
    print(f"Database     : {DB_PATH}")

    try:
        for market, ticker in DEFAULT_SYMBOLS:
            print(f"\nFetching {market.upper()}:{ticker} from FinanceDataReader...")
            result = collector.fetch(
                CollectorRequest(market=market, ticker=ticker, period="6mo", interval="1d")
            )
            print(f"Source       : {result.source}")
            print(f"Rows         : {len(result.data)}")
            print(f"Quality      : {result.quality_score}/100")
            print(f"Message      : {result.message}")

            if result.data.empty:
                continue

            before_count = repository.count(market=market, ticker=ticker)
            saved_count = repository.upsert_many(
                _to_price_bars(market, ticker, result.source, result.data)
            )
            after_count = repository.count(market=market, ticker=ticker)

            latest = result.data.iloc[-1]
            print(f"Latest Date  : {latest['Date']}")
            print(f"Latest Close : {float(latest['Close']):,.2f}")
            print(f"Latest Volume: {int(latest['Volume']):,}")
            print(f"Saved Rows   : {saved_count}")
            print(f"New Rows     : {after_count - before_count}")
            print(f"Total Stored : {after_count}")
    finally:
        repository.close()

    print(f"\nDone. SQLite DataHub saved at: {DB_PATH}")


if __name__ == "__main__":
    main()
