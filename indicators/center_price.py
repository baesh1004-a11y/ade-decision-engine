import pandas as pd


def add_center_price(df: pd.DataFrame) -> pd.DataFrame:
    """Add candle center price and candle body features."""
    out = df.copy()
    out["CENTER"] = (out["Open"] + out["Close"]) / 2
    out["BODY"] = (out["Close"] - out["Open"]).abs()
    out["RANGE"] = (out["High"] - out["Low"]).replace(0, pd.NA)
    out["BODY_RATIO"] = out["BODY"] / out["RANGE"]
    out["IS_BULLISH"] = out["Close"] > out["Open"]
    return out
