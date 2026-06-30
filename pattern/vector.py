import pandas as pd


DEFAULT_VECTOR_COLUMNS = [
    "Close",
    "Volume",
    "MA5",
    "MA20",
    "MA60",
    "MA120",
    "MA240",
    "VOL20_RATIO",
    "BODY_RATIO",
    "STO533_K",
    "STO533_D",
    "STO1066_K",
    "STO1066_D",
    "STO201212_K",
    "STO201212_D",
]


def build_latest_vector(df: pd.DataFrame, columns: list[str] | None = None) -> pd.Series:
    """Build a numeric vector for the latest row of an indicator dataframe."""
    cols = columns or DEFAULT_VECTOR_COLUMNS
    available = [col for col in cols if col in df.columns]
    if not available:
        raise ValueError("No vector columns are available in dataframe.")
    latest = df[available].iloc[-1].astype(float)
    return latest.fillna(0.0)


def build_window_vector(df: pd.DataFrame, window: int = 60, columns: list[str] | None = None) -> pd.Series:
    """Flatten the latest window into one vector.

    This is the base input for future similarity search.
    """
    cols = columns or DEFAULT_VECTOR_COLUMNS
    available = [col for col in cols if col in df.columns]
    if len(df) < window:
        raise ValueError(f"Not enough rows. Need {window}, got {len(df)}")
    window_df = df[available].tail(window).astype(float).fillna(0.0)
    return pd.Series(window_df.to_numpy().flatten())
