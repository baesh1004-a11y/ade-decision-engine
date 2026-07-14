from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from datahub.models import PriceBar
from datahub.repository import PriceRepository
from markets.profiles import get_market_profile
from markets.us_universe import USUniverseFilter, build_us_universe, download_market_history


def main() -> None:
    parser = argparse.ArgumentParser(description="Build filtered, separated ADE US stock database")
    parser.add_argument("--period", default="10y", help="가격 수집 기간. 기본 10y")
    parser.add_argument("--min-market-cap", type=float, default=1_000_000_000, help="최소 시가총액 USD")
    parser.add_argument("--min-dollar-volume", type=float, default=10_000_000, help="최근 평균 일 거래대금 USD")
    parser.add_argument("--min-history-years", type=float, default=3.0, help="최소 가격 이력 연수")
    parser.add_argument("--liquidity-days", type=int, default=60, help="평균 거래대금 계산 기간")
    parser.add_argument("--max-symbols", type=int, default=1500, help="시총 1차 후보 상한. 0이면 무제한")
    parser.add_argument("--tickers", nargs="*", help="지정 시 자동 종목검색 대신 입력 종목만 수집")
    parser.add_argument("--keep-old-symbols", action="store_true", help="필터 탈락 종목의 기존 가격을 DB에 유지")
    args = parser.parse_args()

    profile = get_market_profile("us")
    profile.db_path.parent.mkdir(parents=True, exist_ok=True)

    if args.tickers:
        members = _manual_members(args.tickers, args)
        diagnostics = pd.DataFrame(
            [{"symbol": item["symbol"], "result": "MANUAL"} for item in members]
        )
    else:
        filters = USUniverseFilter(
            min_market_cap=float(args.min_market_cap),
            min_avg_dollar_volume=float(args.min_dollar_volume),
            min_history_years=float(args.min_history_years),
            liquidity_days=max(1, int(args.liquidity_days)),
            max_symbols=max(0, int(args.max_symbols)),
        )
        selected, diagnostics = build_us_universe(filters)
        members = [item.to_dict() for item in selected]

    if not members:
        raise RuntimeError("필터를 통과한 미국 종목이 없습니다.")

    symbols = [str(item["symbol"]).upper() for item in members]
    print("\nUS FILTER SUMMARY")
    print(f"Selected symbols: {len(symbols):,}")
    print(f"Minimum market cap: ${args.min_market_cap:,.0f}")
    print(f"Minimum average dollar volume: ${args.min_dollar_volume:,.0f}")
    print(f"Minimum history: {args.min_history_years:.1f} years")
    print("Excluded: ETF/ETN, ADR/ADS, preferred shares, warrants, rights, units, SPAC")

    history = download_market_history(symbols, period=args.period, chunk_size=75)
    repo = PriceRepository(profile.db_path)
    try:
        _initialize_universe_tables(repo.conn)
        if not args.keep_old_symbols:
            _remove_stale_symbols(repo.conn, symbols)

        total = 0
        successful: list[str] = []
        for index, item in enumerate(members, start=1):
            ticker = str(item["symbol"]).upper()
            frame = history.get(ticker, pd.DataFrame())
            if frame.empty:
                print(f"[{index}/{len(members)}] SKIP {ticker}: no data")
                continue
            records = _price_records(ticker, frame)
            if not records:
                print(f"[{index}/{len(members)}] SKIP {ticker}: invalid data")
                continue
            count = repo.upsert_many(records)
            total += count
            successful.append(ticker)
            _upsert_universe_member(repo.conn, item)
            print(f"[{index}/{len(members)}] OK {ticker}: {count:,} rows")

        _disable_missing_members(repo.conn, successful)
        repo.conn.commit()
        _write_reports(profile.db_path, members, diagnostics, args)

        print("\nUS DATABASE COMPLETED")
        print(f"DB: {profile.db_path}")
        print(f"Updated: {date.today().isoformat()}")
        print(f"Selected: {len(symbols):,}")
        print(f"Downloaded: {len(successful):,}")
        print(f"Rows written: {total:,}")
        print("Reports: output/us_universe_selected.csv, output/us_universe_diagnostics.csv")
        print("Replay events and vectors must be built separately in datahub/us_market.db.")
    finally:
        repo.close()


def _manual_members(tickers: list[str], args: argparse.Namespace) -> list[dict[str, object]]:
    history = download_market_history(tickers, period="5y", chunk_size=75)
    members: list[dict[str, object]] = []
    for symbol in dict.fromkeys(ticker.upper() for ticker in tickers):
        frame = history.get(symbol, pd.DataFrame())
        if frame.empty:
            continue
        valid = pd.DataFrame(
            {
                "Close": pd.to_numeric(frame.get("Close"), errors="coerce"),
                "Volume": pd.to_numeric(frame.get("Volume"), errors="coerce"),
            }
        ).dropna()
        if valid.empty:
            continue
        recent = valid.tail(max(1, int(args.liquidity_days)))
        members.append(
            {
                "symbol": symbol,
                "name": symbol,
                "exchange": "MANUAL",
                "market_cap": 0.0,
                "avg_dollar_volume": float((recent["Close"] * recent["Volume"]).mean()),
                "history_years": max(0.0, (valid.index.max() - valid.index.min()).days / 365.25),
                "ipo_year": None,
                "sector": None,
                "industry": None,
            }
        )
    return members


def _price_records(ticker: str, frame: pd.DataFrame) -> list[PriceBar]:
    records: list[PriceBar] = []
    for stamp, row in frame.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).iterrows():
        adjusted = row.get("Adj Close", row["Close"])
        records.append(
            PriceBar(
                market="us",
                ticker=ticker,
                trade_date=str(pd.Timestamp(stamp).date()),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
                adjusted_close=float(adjusted) if pd.notna(adjusted) else float(row["Close"]),
                source="yfinance",
            )
        )
    return records


def _initialize_universe_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS us_universe (
            symbol TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            exchange TEXT,
            market_cap REAL NOT NULL DEFAULT 0,
            avg_dollar_volume REAL NOT NULL DEFAULT 0,
            history_years REAL NOT NULL DEFAULT 0,
            ipo_year INTEGER,
            sector TEXT,
            industry TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            selected_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_us_universe_enabled
            ON us_universe(enabled, market_cap DESC);
        CREATE TABLE IF NOT EXISTS us_universe_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            selected_count INTEGER NOT NULL,
            filter_json TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _upsert_universe_member(conn: sqlite3.Connection, item: dict[str, object]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO us_universe(
            symbol, name, exchange, market_cap, avg_dollar_volume,
            history_years, ipo_year, sector, industry, enabled,
            selected_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            name=excluded.name,
            exchange=excluded.exchange,
            market_cap=excluded.market_cap,
            avg_dollar_volume=excluded.avg_dollar_volume,
            history_years=excluded.history_years,
            ipo_year=excluded.ipo_year,
            sector=excluded.sector,
            industry=excluded.industry,
            enabled=1,
            updated_at=excluded.updated_at
        """,
        (
            item["symbol"], item.get("name") or item["symbol"], item.get("exchange"),
            float(item.get("market_cap") or 0), float(item.get("avg_dollar_volume") or 0),
            float(item.get("history_years") or 0), item.get("ipo_year"),
            item.get("sector"), item.get("industry"), now, now,
        ),
    )


def _disable_missing_members(conn: sqlite3.Connection, successful: list[str]) -> None:
    conn.execute("UPDATE us_universe SET enabled=0")
    if not successful:
        return
    placeholders = ",".join("?" for _ in successful)
    conn.execute(
        f"UPDATE us_universe SET enabled=1, updated_at=? WHERE symbol IN ({placeholders})",
        [datetime.now().isoformat(timespec="seconds"), *successful],
    )


def _remove_stale_symbols(conn: sqlite3.Connection, selected: list[str]) -> None:
    if not selected:
        return
    placeholders = ",".join("?" for _ in selected)
    conn.execute(
        f"DELETE FROM price_bars WHERE market='us' AND ticker NOT IN ({placeholders})",
        selected,
    )
    conn.commit()


def _write_reports(
    db_path: Path,
    members: list[dict[str, object]],
    diagnostics: pd.DataFrame,
    args: argparse.Namespace,
) -> None:
    output = Path("output")
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(members).to_csv(output / "us_universe_selected.csv", index=False, encoding="utf-8-sig")
    diagnostics.to_csv(output / "us_universe_diagnostics.csv", index=False, encoding="utf-8-sig")

    conn = sqlite3.connect(str(db_path))
    try:
        now = datetime.now()
        conn.execute(
            "INSERT INTO us_universe_runs(run_id, started_at, selected_count, filter_json) VALUES (?, ?, ?, ?)",
            (
                f"US-{now.strftime('%Y%m%dT%H%M%S')}",
                now.isoformat(timespec="seconds"),
                len(members),
                json.dumps(
                    {
                        "period": args.period,
                        "min_market_cap": args.min_market_cap,
                        "min_dollar_volume": args.min_dollar_volume,
                        "min_history_years": args.min_history_years,
                        "liquidity_days": args.liquidity_days,
                        "max_symbols": args.max_symbols,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
