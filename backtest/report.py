import pandas as pd

from backtest.engine import summarize_backtest


def format_summary(summary: dict) -> str:
    """Format backtest summary as readable text."""
    if summary.get("signals", 0) == 0:
        return "No signals generated."

    return "\n".join([
        "Backtest Summary",
        "================",
        f"Signals       : {summary['signals']}",
        f"Win Rate      : {summary['win_rate']:.2f}%",
        f"Avg Return    : {summary['avg_return']:.2f}%",
        f"Median Return : {summary['median_return']:.2f}%",
        f"Max Return    : {summary['max_return']:.2f}%",
        f"Min Return    : {summary['min_return']:.2f}%",
    ])


def make_report(result: pd.DataFrame) -> str:
    """Create a backtest text report."""
    summary = summarize_backtest(result)
    return format_summary(summary)
