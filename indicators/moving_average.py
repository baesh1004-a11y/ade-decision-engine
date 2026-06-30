import pandas as pd


def add_moving_averages(df: pd.DataFrame, periods: tuple[int, ...] = (5, 20, 60, 120, 240)) -> pd.DataFrame:
    """Add moving average columns based on Close price."""
    out = df.copy()
    for period in periods:
        out[f"MA{period}"] = out["Close"].rolling(period).mean()
        out[f"MA{period}_SLOPE"] = out[f"MA{period}"].diff()
    return out
