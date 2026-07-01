"""ADE - AI Decision Engine command-line runner."""

from __future__ import annotations

import argparse
from datetime import datetime

from backtest.engine import run_backtest, summarize_backtest
from backtest.report import format_summary
from collector.korea import KoreaCollector
from collector.usa import USACollector
from indicators.pipeline import add_all_indicators
from strategy.candidate import score_latest


DEFAULT_KOREA_TICKER = "005930"
DEFAULT_USA_TICKER = "NVDA"


def load_market_data(market: str, ticker: str, start: str, end: str):
    """Load OHLCV data from the selected market."""
    if market == "kr":
        return KoreaCollector().get_daily(ticker=ticker, start=start, end=end)
    if market == "us":
        return USACollector().get_daily(ticker=ticker, period="10y", interval="1d")
    raise ValueError("market must be one of: kr, us")


def run_single_analysis(market: str, ticker: str, start: str, end: str) -> None:
    """Run collection, indicators, scoring, and backtest summary."""
    print("=" * 60)
    print("ADE (AI Decision Engine)")
    print("=" * 60)
    print(f"Start Time : {datetime.now()}")
    print(f"Market     : {market}")
    print(f"Ticker     : {ticker}")

    df = load_market_data(market=market, ticker=ticker, start=start, end=end)
    enriched = add_all_indicators(df)
    latest = score_latest(enriched)

    print("\nLatest Candidate Decision")
    print("-------------------------")
    print(f"Engine     : {latest['engine_version']}")
    print(f"Close      : {latest['close']:.2f}")
    print(f"Score      : {latest['score']}/100")
    print(f"Grade      : {latest['grade']}")
    print(f"Action     : {latest['action']}")
    print(f"Confidence : {latest['confidence']:.2f}")
    print(f"Risk Level : {latest['risk_level']}")
    if latest["risk_flags"]:
        print("Risk Flags :")
        for flag in latest["risk_flags"]:
            print(f"- {flag}")
    print("Reasons    :")
    for reason in latest["reasons"]:
        print(f"- {reason}")

    bt = run_backtest(df, min_score=70)
    summary = summarize_backtest(bt)
    print("\n" + format_summary(summary))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ADE v0.2 single ticker analysis")
    parser.add_argument("--market", choices=["kr", "us"], default="kr")
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--start", default="20200101")
    parser.add_argument("--end", default="20261231")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ticker = args.ticker or (DEFAULT_KOREA_TICKER if args.market == "kr" else DEFAULT_USA_TICKER)
    run_single_analysis(market=args.market, ticker=ticker, start=args.start, end=args.end)


if __name__ == "__main__":
    main()
