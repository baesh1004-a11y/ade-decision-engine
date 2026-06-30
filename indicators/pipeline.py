import pandas as pd

from indicators.center_price import add_center_price
from indicators.moving_average import add_moving_averages
from indicators.stochastic import add_all_stochastic
from indicators.volume import add_volume_features


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Run the standard ADE indicator pipeline."""
    out = df.copy()
    out = add_moving_averages(out)
    out = add_volume_features(out)
    out = add_center_price(out)
    out = add_all_stochastic(out)
    return out
