from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from data.providers import HybridProvider
from datahub.models import PriceBar
from datahub.provenance import DataProvenanceStore
from datahub.repository import PriceRepository
from universe.manager import DynamicUniverseManager
from universe.models import UniverseSymbol


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


def _fetch_symbol(symbol: UniverseSymbol, period: str, retries: int) -> tuple[UniverseSymbol, object]:
    provider = HybridProvider()
    last_result = None
    for attempt in range(1, retries + 1):
        result = provider.fetch_history(symbol.market, symbol.ticker, period=period)
        last_result = result
        if not result.data.empty:
            return symbol, result
        time.sleep(0.2 * attempt)
    return symbol, last_result


def main() -> None:
    parser = argparse.ArgumentParser(description="ADE full data collection")
    parser.add_argument("--market", choices=["kr", "us", "all"], default="kr")
    parser.add_argument("--period", default="5y")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="debug only; 0 means no limit")
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    provider = HybridProvider()
    repository = PriceRepository(DB_PATH)
    provenance = DataProvenanceStore(DB_PATH)

    symbols = DynamicUniverseManager().active(None if args.market == "all" else args.market)
    if args.limit > 0:
        symbols = symbols[: args.limit]

    run_id = provenance.start_run(
        historical_source="FDR",
        realtime_source="KIS",
        database_source="SQLite DataHub",
        target_count=len(symbols),
    )

    print("\n==============================")
    print("     ADE DATA COLLECTION v3")
    print("==============================")
    print(f"Database       : {DB_PATH}")
    print("Historical     : FDR")
    print("Realtime       : KIS")
    print("Replay DB      : SQLite DataHub")
    print(f"Market         : {args.market.upper()}")
    print(f"Period         : {args.period}")
    print(f"Targets        : {len(symbols)}")
    print(f"Workers        : {args.workers}")
    print("KIS Status")
    for key, value in provider.status().items():
        print(f"- {key}: {value}")

    success = 0
    fail = 0
    total_rows = 0
    failed: list[str] = []

    try:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = [executor.submit(_fetch_symbol, symbol, args.period, args.retries) for symbol in symbols]
            for index, future in enumerate(as_completed(futures), start=1):
                symbol, result = future.result()
                label = f"{symbol.market.upper()}:{symbol.ticker} {symbol.name or ''}".strip()
                if result is None or result.data.empty:
                    fail += 1
                    failed.append(label)
                    print(f"[{index}/{len(symbols)}] {label}  FAIL")
                    continue

                saved_count = repository.upsert_many(_to_price_bars(symbol.market, symbol.ticker, result.source, result.data))
                success += 1
                total_rows += saved_count
                latest = result.data.iloc[-1]
                print(
                    f"[{index}/{len(symbols)}] {label}  OK  "
                    f"source={result.source} rows={len(result.data)} quality={result.quality_score}/100 "
                    f"latest={pd.Timestamp(latest['Date']).date()} close={float(latest['Close']):,.2f}"
                )
    finally:
        repository.close()
        provenance.finish_run(run_id, success_count=success, fail_count=fail, total_rows=total_rows, status="DONE")
        provenance.close()

    print("\n==============================")
    print("     COLLECTION SUMMARY")
    print("==============================")
    print(f"Targets        : {len(symbols)}")
    print(f"Success        : {success}")
    print(f"Failed         : {fail}")
    print(f"Saved Rows     : {total_rows}")
    print("Historical     : FDR")
    print("Realtime       : KIS")
    print("Replay DB      : SQLite DataHub")
    if failed:
        Path("reports").mkdir(exist_ok=True)
        failed_path = Path("reports/failed_collection.txt")
        failed_path.write_text("\n".join(failed), encoding="utf-8")
        print(f"Failed List    : {failed_path}")
    print(f"\nDone. SQLite DataHub saved at: {DB_PATH}")


if __name__ == "__main__":
    main()
