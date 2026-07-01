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
from strategy.entry import EntryTimingEngine
from strategy.position_sizing import AccountState, PositionSizingInput, PositionSizingEngine


DEFAULT_KOREA_TICKER = "005930"
DEFAULT_USA_TICKER = "NVDA"


def load_market_data(market: str, ticker: str, start: str, end: str):
    """Load OHLCV data from the selected market."""
    if market == "kr":
        return KoreaCollector().get_daily(ticker=ticker, start=start, end=end)
    if market == "us":
        return USACollector().get_daily(ticker=ticker, period="10y", interval="1d")
    raise ValueError("market must be one of: kr, us")


def _latest_atr_like_value(enriched) -> float | None:
    """Return an ATR-like value when the indicator pipeline has one.

    The current indicator pipeline may not always include ATR. This helper keeps
    the CLI backward compatible and lets the PSE run with volatility adjustment
    when an ATR column is available later.
    """
    for column in ["ATR", "ATR14", "atr", "atr14"]:
        if column in enriched.columns:
            value = enriched.iloc[-1][column]
            if value == value:
                return float(value)
    return None


def run_single_analysis(
    market: str,
    ticker: str,
    start: str,
    end: str,
    account_balance: float,
    cash: float | None,
    market_regime: str,
) -> None:
    """Run collection, indicators, scoring, sizing, entry timing, and backtest summary."""
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

    sizing = PositionSizingEngine().recommend(
        PositionSizingInput(
            ticker=ticker,
            price=float(latest["close"]),
            grade=str(latest["grade"]),
            confidence=float(latest["confidence"]),
            risk_level=str(latest["risk_level"]),
            atr=_latest_atr_like_value(enriched),
            market_regime=market_regime,
            account=AccountState(
                account_balance=account_balance,
                cash=cash if cash is not None else account_balance,
            ),
        )
    )

    print("\nPosition Sizing Recommendation")
    print("------------------------------")
    print(f"Engine      : {sizing.engine_version}")
    print(f"Weight      : {sizing.recommended_weight:.2%}")
    print(f"Buy Amount  : {sizing.buy_amount:,.0f}")
    print(f"Shares      : {sizing.shares:,}")
    print(f"Max Loss    : {sizing.max_loss:,.0f}")
    print(f"Risk Score  : {sizing.risk_score}/100")
    print(f"Cash Limited: {sizing.cash_limited}")
    print("Reasons     :")
    for reason in sizing.reasons:
        print(f"- {reason}")

    entry = EntryTimingEngine().evaluate(
        enriched,
        candidate=latest,
        position=sizing.to_dict(),
        market_regime=market_regime,
    )

    print("\nEntry Timing Decision")
    print("---------------------")
    print(f"Engine     : {entry.engine_version}")
    print(f"Score      : {entry.entry_score}/100")
    print(f"Action     : {entry.action}")
    print(f"Order Type : {entry.order_type}")
    print(f"Entry Price: {entry.entry_price:,.2f}")
    print(f"Limit Price: {entry.limit_price:,.2f}")
    print(f"Risk Level : {entry.risk_level}")
    if entry.risk_flags:
        print("Risk Flags :")
        for flag in entry.risk_flags:
            print(f"- {flag}")
    print("Reasons    :")
    for reason in entry.reasons:
        print(f"- {reason}")

    bt = run_backtest(df, min_score=70)
    summary = summarize_backtest(bt)
    print("\n" + format_summary(summary))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ADE v1.0 single ticker analysis")
    parser.add_argument("--market", choices=["kr", "us"], default="kr")
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--start", default="20200101")
    parser.add_argument("--end", default="20261231")
    parser.add_argument("--account-balance", type=float, default=100_000_000)
    parser.add_argument("--cash", type=float, default=None)
    parser.add_argument("--market-regime", choices=["BULL", "SIDEWAY", "BEAR"], default="SIDEWAY")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ticker = args.ticker or (DEFAULT_KOREA_TICKER if args.market == "kr" else DEFAULT_USA_TICKER)
    run_single_analysis(
        market=args.market,
        ticker=ticker,
        start=args.start,
        end=args.end,
        account_balance=args.account_balance,
        cash=args.cash,
        market_regime=args.market_regime,
    )


if __name__ == "__main__":
    main()
