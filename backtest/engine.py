import pandas as pd

from indicators.pipeline import add_all_indicators
from strategy.candidate import score_latest


DEFAULT_HORIZONS = (5, 10, 20, 40, 60, 120)


def future_return(df: pd.DataFrame, index: int, horizon: int = 20) -> float | None:
    """Calculate future return from index to index+horizon."""
    if index + horizon >= len(df):
        return None
    entry = float(df.iloc[index]["Close"])
    exit_price = float(df.iloc[index + horizon]["Close"])
    if entry == 0:
        return None
    return float((exit_price / entry - 1) * 100)


def future_mdd(df: pd.DataFrame, index: int, horizon: int = 20) -> float | None:
    """Calculate max drawdown after signal over the future horizon."""
    if index + horizon >= len(df):
        return None
    entry = float(df.iloc[index]["Close"])
    lows = df.iloc[index + 1 : index + horizon + 1]["Low"].astype(float)
    if entry == 0 or lows.empty:
        return None
    return float((lows.min() / entry - 1) * 100)


def run_backtest(
    df: pd.DataFrame,
    min_score: int = 70,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> pd.DataFrame:
    """Run a rolling backtest using ADE candidate score.

    For each day, the engine calculates indicators using data available up to
    that day, scores the latest row, and records future returns over multiple
    horizons.
    """
    data = add_all_indicators(df)
    max_horizon = max(horizons)
    results: list[dict] = []

    for i in range(240, len(data) - max_horizon):
        window = data.iloc[: i + 1].copy()
        decision = score_latest(window)
        score = decision["score"]

        if score >= min_score:
            record = {
                "Date": data.iloc[i]["Date"],
                "Close": float(data.iloc[i]["Close"]),
                "EngineVersion": decision.get("engine_version"),
                "Score": score,
                "Grade": decision.get("grade"),
                "Action": decision.get("action"),
                "Confidence": decision.get("confidence"),
                "RiskLevel": decision.get("risk_level"),
                "RiskFlags": "; ".join(decision.get("risk_flags", [])),
                "Reasons": "; ".join(decision.get("reasons", [])),
            }
            for horizon in horizons:
                record[f"Return_{horizon}D"] = future_return(data, i, horizon)
                record[f"MDD_{horizon}D"] = future_mdd(data, i, horizon)
            results.append(record)

    return pd.DataFrame(results)


def summarize_backtest(result: pd.DataFrame, primary_horizon: int = 20) -> dict:
    """Summarize backtest result dataframe."""
    target_col = f"Return_{primary_horizon}D"
    mdd_col = f"MDD_{primary_horizon}D"

    if result.empty or target_col not in result.columns:
        return {
            "signals": 0,
            "primary_horizon": primary_horizon,
            "win_rate": None,
            "avg_return": None,
            "median_return": None,
            "avg_mdd": None,
        }

    returns = result[target_col].dropna()
    mdds = result[mdd_col].dropna() if mdd_col in result.columns else pd.Series(dtype=float)
    if returns.empty:
        return {
            "signals": 0,
            "primary_horizon": primary_horizon,
            "win_rate": None,
            "avg_return": None,
            "median_return": None,
            "avg_mdd": None,
        }

    gains = returns[returns > 0]
    losses = returns[returns < 0]
    profit_factor = None
    if not losses.empty:
        profit_factor = float(gains.sum() / abs(losses.sum())) if not gains.empty else 0.0

    return {
        "signals": int(len(returns)),
        "primary_horizon": primary_horizon,
        "win_rate": float((returns > 0).mean() * 100),
        "avg_return": float(returns.mean()),
        "median_return": float(returns.median()),
        "max_return": float(returns.max()),
        "min_return": float(returns.min()),
        "avg_mdd": float(mdds.mean()) if not mdds.empty else None,
        "profit_factor": profit_factor,
    }
