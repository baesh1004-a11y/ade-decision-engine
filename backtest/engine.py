import pandas as pd

from indicators.pipeline import add_all_indicators
from strategy.candidate import score_latest


def future_return(df: pd.DataFrame, index: int, horizon: int = 20) -> float | None:
    """Calculate future return from index to index+horizon."""
    if index + horizon >= len(df):
        return None
    entry = df.iloc[index]["Close"]
    exit_price = df.iloc[index + horizon]["Close"]
    if entry == 0:
        return None
    return float((exit_price / entry - 1) * 100)


def run_backtest(df: pd.DataFrame, min_score: int = 70, horizon: int = 20) -> pd.DataFrame:
    """Run a simple rolling backtest using ADE candidate score.

    For each day, the engine calculates indicators using data available up to
    that day, scores the latest row, and records the future return.
    """
    data = add_all_indicators(df)
    results: list[dict] = []

    for i in range(240, len(data) - horizon):
        window = data.iloc[: i + 1].copy()
        decision = score_latest(window)
        score = decision["score"]

        if score >= min_score:
            ret = future_return(data, i, horizon)
            results.append({
                "Date": data.iloc[i]["Date"],
                "Close": float(data.iloc[i]["Close"]),
                "Score": score,
                "Horizon": horizon,
                "FutureReturnPct": ret,
                "Reasons": "; ".join(decision["reasons"]),
            })

    return pd.DataFrame(results)


def summarize_backtest(result: pd.DataFrame) -> dict:
    """Summarize backtest result dataframe."""
    if result.empty:
        return {
            "signals": 0,
            "win_rate": None,
            "avg_return": None,
            "median_return": None,
        }

    returns = result["FutureReturnPct"].dropna()
    return {
        "signals": int(len(returns)),
        "win_rate": float((returns > 0).mean() * 100),
        "avg_return": float(returns.mean()),
        "median_return": float(returns.median()),
        "max_return": float(returns.max()),
        "min_return": float(returns.min()),
    }
