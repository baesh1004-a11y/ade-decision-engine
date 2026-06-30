import pandas as pd


def add_volume_features(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Add volume moving average and volume ratio."""
    out = df.copy()
    out[f"VOL{window}_AVG"] = out["Volume"].rolling(window).mean()
    out[f"VOL{window}_RATIO"] = out["Volume"] / out[f"VOL{window}_AVG"]
    return out
