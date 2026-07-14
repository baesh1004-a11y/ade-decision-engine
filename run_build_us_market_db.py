from __future__ import annotations

import argparse
from datetime import date

import yfinance as yf

from datahub.models import PriceBar
from datahub.repository import PriceRepository
from markets.profiles import get_market_profile


DEFAULT_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO",
    "COST", "AMD", "NFLX", "QCOM", "ADBE", "TXN", "AMGN", "ISRG",
    "HON", "INTU", "BKNG", "PANW", "MDLZ", "VRTX", "REGN", "GILD",
    "ADI", "ADP", "MELI", "LRCX", "MU", "PLTR",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build separated ADE US price database")
    parser.add_argument("--period", default="10y")
    parser.add_argument("--tickers", nargs="*", default=DEFAULT_TICKERS)
    args = parser.parse_args()

    profile = get_market_profile("us")
    repo = PriceRepository(profile.db_path)
    try:
        total = 0
        for ticker in args.tickers:
            frame = yf.Ticker(ticker).history(period=args.period, interval="1d", auto_adjust=False)
            if frame.empty:
                print(f"SKIP {ticker}: no data")
                continue
            if getattr(frame.index, "tz", None) is not None:
                frame.index = frame.index.tz_localize(None)
            records: list[PriceBar] = []
            for stamp, row in frame.iterrows():
                records.append(
                    PriceBar(
                        market="us",
                        ticker=ticker.upper(),
                        trade_date=str(stamp.date()),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=float(row["Volume"]),
                        adjusted_close=float(row.get("Adj Close", row["Close"])),
                        source="yfinance",
                    )
                )
            count = repo.upsert_many(records)
            total += count
            print(f"OK {ticker}: {count:,} rows")
        print(f"US DB: {profile.db_path}")
        print(f"Updated: {date.today().isoformat()}")
        print(f"Rows written: {total:,}")
        print("Price DB build completed. Replay events/vectors must be built in this US DB before recommendations are available.")
    finally:
        repo.close()


if __name__ == "__main__":
    main()
