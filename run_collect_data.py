from __future__ import annotations

from collector.base import CollectorRequest
from collector.fdr import FDRCollector


DEFAULT_SYMBOLS = [
    ("us", "NVDA"),
    ("us", "MSFT"),
    ("us", "AAPL"),
    ("kr", "005930"),
    ("kr", "000660"),
]


def main() -> None:
    collector = FDRCollector()

    print("\n==============================")
    print("     ADE DATA COLLECTION v1")
    print("==============================")

    for market, ticker in DEFAULT_SYMBOLS:
        print(f"\nFetching {market.upper()}:{ticker} from FinanceDataReader...")
        result = collector.fetch(
            CollectorRequest(market=market, ticker=ticker, period="6mo", interval="1d")
        )
        print(f"Source       : {result.source}")
        print(f"Rows         : {len(result.data)}")
        print(f"Quality      : {result.quality_score}/100")
        print(f"Message      : {result.message}")
        if not result.data.empty:
            latest = result.data.iloc[-1]
            print(f"Latest Date  : {latest['Date']}")
            print(f"Latest Close : {float(latest['Close']):,.2f}")
            print(f"Latest Volume: {int(latest['Volume']):,}")


if __name__ == "__main__":
    main()
