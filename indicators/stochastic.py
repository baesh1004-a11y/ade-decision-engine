import pandas as pd


def add_stochastic(df: pd.DataFrame, k_period: int, k_smooth: int, d_smooth: int, prefix: str) -> pd.DataFrame:
    """Add stochastic oscillator columns to an OHLCV dataframe.

    The output columns are:
    - {prefix}_K_RAW
    - {prefix}_K
    - {prefix}_D
    """
    out = df.copy()
    low_min = out["Low"].rolling(k_period).min()
    high_max = out["High"].rolling(k_period).max()
    denominator = (high_max - low_min).replace(0, pd.NA)

    out[f"{prefix}_K_RAW"] = ((out["Close"] - low_min) / denominator) * 100
    out[f"{prefix}_K"] = out[f"{prefix}_K_RAW"].rolling(k_smooth).mean()
    out[f"{prefix}_D"] = out[f"{prefix}_K"].rolling(d_smooth).mean()
    return out


def add_all_stochastic(df: pd.DataFrame) -> pd.DataFrame:
    """Add ADE standard STO 5-3-3, 10-6-6, 20-12-12."""
    out = add_stochastic(df, 5, 3, 3, "STO533")
    out = add_stochastic(out, 10, 6, 6, "STO1066")
    out = add_stochastic(out, 20, 12, 12, "STO201212")
    return out
