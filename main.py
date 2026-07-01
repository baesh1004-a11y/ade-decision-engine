"""ADE - AI Decision Engine command-line runner."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from backtest.engine import run_backtest, summarize_backtest
from backtest.report import format_summary
from collector.korea import KoreaCollector
from collector.usa import USACollector
from core.context import DecisionContext
from core.pipeline import ADEPipeline


DEFAULT_KOREA_TICKER = "005930"
DEFAULT_USA_TICKER = "NVDA"


def load_market_data(market: str, ticker: str, start: str, end: str):
    """Load OHLCV data from the selected market."""
    if market == "kr":
        return KoreaCollector().get_daily(ticker=ticker, start=start, end=end)
    if market == "us":
        return USACollector().get_daily(ticker=ticker, period="10y", interval="1d")
    raise ValueError("market must be one of: kr, us")


def _print_list(title: str, values: list[str]) -> None:
    if values:
        print(f"{title}:")
        for value in values:
            print(f"- {value}")


def _print_candidate(decision: dict[str, Any]) -> None:
    print("\nLatest Candidate Decision")
    print("-------------------------")
    print(f"Engine     : {decision['engine_version']}")
    print(f"Close      : {decision['close']:.2f}")
    print(f"Score      : {decision['score']}/100")
    print(f"Grade      : {decision['grade']}")
    print(f"Action     : {decision['action']}")
    print(f"Confidence : {decision['confidence']:.2f}")
    print(f"Risk Level : {decision['risk_level']}")
    _print_list("Risk Flags", decision.get("risk_flags", []))
    _print_list("Reasons", decision.get("reasons", []))


def _print_risk(decision: dict[str, Any]) -> None:
    print("\nRisk Decision")
    print("-------------")
    print(f"Engine              : {decision['engine_version']}")
    print(f"Risk Score          : {decision['risk_score']}/100")
    print(f"Risk Level          : {decision['risk_level']}")
    print(f"Action              : {decision['action']}")
    print(f"Trade Allowed       : {decision['trade_allowed']}")
    print(f"Max New Position    : {decision['max_new_position_weight']:.2%}")
    print(f"Target Cash Weight  : {decision['target_cash_weight']:.2%}")
    print(f"Daily Loss          : {decision['daily_loss_pct']:.2%}")
    print(f"Drawdown            : {decision['drawdown_pct']:.2%}")
    _print_list("Risk Flags", decision.get("risk_flags", []))
    _print_list("Reasons", decision.get("reasons", []))


def _print_position(decision: dict[str, Any]) -> None:
    print("\nPosition Sizing Recommendation")
    print("------------------------------")
    print(f"Engine      : {decision['engine_version']}")
    print(f"Weight      : {decision['recommended_weight']:.2%}")
    print(f"Buy Amount  : {decision['buy_amount']:,.0f}")
    print(f"Shares      : {decision['shares']:,}")
    print(f"Max Loss    : {decision['max_loss']:,.0f}")
    print(f"Risk Score  : {decision['risk_score']}/100")
    print(f"Cash Limited: {decision['cash_limited']}")
    if decision.get("risk_capped"):
        print("Risk Capped : True")
    _print_list("Reasons", decision.get("reasons", []))


def _print_entry(decision: dict[str, Any]) -> None:
    print("\nEntry Timing Decision")
    print("---------------------")
    print(f"Engine     : {decision['engine_version']}")
    print(f"Score      : {decision['entry_score']}/100")
    print(f"Action     : {decision['action']}")
    print(f"Order Type : {decision['order_type']}")
    print(f"Entry Price: {decision['entry_price']:,.2f}")
    print(f"Limit Price: {decision['limit_price']:,.2f}")
    print(f"Risk Level : {decision['risk_level']}")
    _print_list("Risk Flags", decision.get("risk_flags", []))
    _print_list("Reasons", decision.get("reasons", []))


def _print_exit(decision: dict[str, Any]) -> None:
    print("\nExit Decision")
    print("-------------")
    print(f"Engine          : {decision['engine_version']}")
    print(f"Sell Score      : {decision['sell_score']}/100")
    print(f"Action          : {decision['action']}")
    print(f"Sell Ratio      : {decision['sell_ratio']:.2%}")
    print(f"Sell Shares     : {decision['sell_shares']:,}")
    print(f"Remaining Shares: {decision['remaining_shares']:,}")
    print(f"Current Price   : {decision['current_price']:,.2f}")
    print(f"PnL             : {decision['pnl_pct']:.2%}")
    print(f"Risk Level      : {decision['risk_level']}")
    _print_list("Risk Flags", decision.get("risk_flags", []))
    _print_list("Reasons", decision.get("reasons", []))


def run_single_analysis(
    market: str,
    ticker: str,
    start: str,
    end: str,
    account_balance: float,
    cash: float | None,
    market_regime: str,
    vix: float | None,
    equity_peak: float | None,
    daily_pnl: float,
    portfolio_heat: float,
    entry_price: float | None,
    holding_shares: int | None,
    highest_price: float | None,
    holding_days: int,
    stop_loss_price: float | None,
) -> None:
    """Run ADE integrated decision pipeline and backtest summary."""
    print("=" * 60)
    print("ADE (AI Decision Engine) - Integrated Pipeline")
    print("=" * 60)
    print(f"Start Time : {datetime.now()}")
    print(f"Market     : {market}")
    print(f"Ticker     : {ticker}")

    df = load_market_data(market=market, ticker=ticker, start=start, end=end)
    current_position = None
    if entry_price is not None and holding_shares is not None:
        current_position = {
            "entry_price": entry_price,
            "shares": holding_shares,
            "highest_price": highest_price,
            "holding_days": holding_days,
            "stop_loss_price": stop_loss_price,
        }

    context = DecisionContext(
        market=market,
        ticker=ticker,
        market_data=df,
        account_balance=account_balance,
        cash=cash if cash is not None else account_balance,
        market_regime=market_regime,
        vix=vix,
        equity_peak=equity_peak or account_balance,
        daily_pnl=daily_pnl,
        portfolio_heat=portfolio_heat,
        current_position=current_position,
    )
    result = ADEPipeline().run(context)
    decisions = result.decisions

    _print_candidate(decisions["candidate"])
    _print_risk(decisions["risk"])
    _print_position(decisions["position"])
    _print_entry(decisions["entry"])
    if "exit" in decisions:
        _print_exit(decisions["exit"])
    _print_list("Pipeline Errors", result.errors)

    bt = run_backtest(df, min_score=70)
    summary = summarize_backtest(bt)
    print("\n" + format_summary(summary))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ADE v1.0 integrated single ticker analysis")
    parser.add_argument("--market", choices=["kr", "us"], default="kr")
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--start", default="20200101")
    parser.add_argument("--end", default="20261231")
    parser.add_argument("--account-balance", type=float, default=100_000_000)
    parser.add_argument("--cash", type=float, default=None)
    parser.add_argument("--market-regime", choices=["BULL", "SIDEWAY", "BEAR"], default="SIDEWAY")
    parser.add_argument("--vix", type=float, default=None)
    parser.add_argument("--equity-peak", type=float, default=None)
    parser.add_argument("--daily-pnl", type=float, default=0.0)
    parser.add_argument("--portfolio-heat", type=float, default=0.0)
    parser.add_argument("--entry-price", type=float, default=None)
    parser.add_argument("--holding-shares", type=int, default=None)
    parser.add_argument("--highest-price", type=float, default=None)
    parser.add_argument("--holding-days", type=int, default=0)
    parser.add_argument("--stop-loss-price", type=float, default=None)
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
        vix=args.vix,
        equity_peak=args.equity_peak,
        daily_pnl=args.daily_pnl,
        portfolio_heat=args.portfolio_heat,
        entry_price=args.entry_price,
        holding_shares=args.holding_shares,
        highest_price=args.highest_price,
        holding_days=args.holding_days,
        stop_loss_price=args.stop_loss_price,
    )


if __name__ == "__main__":
    main()
