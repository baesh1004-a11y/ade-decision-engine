import pandas as pd

from backtest.engine import summarize_backtest


def _fmt_optional_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _fmt_optional_num(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def format_summary(summary: dict) -> str:
    """Format backtest summary as readable text."""
    if summary.get("signals", 0) == 0:
        return "No signals generated."

    return "\n".join([
        "Backtest Summary",
        "================",
        f"Primary Horizon : {summary.get('primary_horizon', 20)}D",
        f"Signals         : {summary['signals']}",
        f"Win Rate        : {_fmt_optional_pct(summary.get('win_rate'))}",
        f"Avg Return      : {_fmt_optional_pct(summary.get('avg_return'))}",
        f"Median Return   : {_fmt_optional_pct(summary.get('median_return'))}",
        f"Max Return      : {_fmt_optional_pct(summary.get('max_return'))}",
        f"Min Return      : {_fmt_optional_pct(summary.get('min_return'))}",
        f"Avg MDD         : {_fmt_optional_pct(summary.get('avg_mdd'))}",
        f"Profit Factor   : {_fmt_optional_num(summary.get('profit_factor'))}",
    ])


def make_report(result: pd.DataFrame, primary_horizon: int = 20) -> str:
    """Create a backtest text report."""
    summary = summarize_backtest(result, primary_horizon=primary_horizon)
    return format_summary(summary)
