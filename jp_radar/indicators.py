from __future__ import annotations

import pandas as pd


def process_daily(df: pd.DataFrame) -> pd.DataFrame:
    processed = df.dropna().copy()
    if getattr(processed.index, "tz", None) is not None:
        processed.index = processed.index.tz_localize(None)
    return processed


def resample_to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    out = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out


def stochastic_energy(series: pd.Series, period: int, smooth_k: int, smooth_d: int) -> tuple[pd.Series, pd.Series]:
    low = series.rolling(window=period, min_periods=1).min()
    high = series.rolling(window=period, min_periods=1).max()
    fast_k_raw = 100.0 * ((series - low) / (high - low + 1e-9))
    k = fast_k_raw.ewm(span=smooth_k, adjust=False).mean() / 10.0
    d = k.ewm(span=smooth_d, adjust=False).mean()
    return k, d


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series]:
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def calculate_signals(index_series: pd.Series, macd_line: pd.Series, signal_line: pd.Series, s_k: pd.Series) -> tuple[pd.Series, pd.Series]:
    div_window = 10
    price_diff = index_series - index_series.shift(div_window)
    macd_diff = macd_line - macd_line.shift(div_window)
    bullish_div = (price_diff <= 0) & (macd_diff >= 0)
    bearish_div = (price_diff >= 0) & (macd_diff <= 0)
    s_k_up = s_k > s_k.shift(1)
    s_k_down = s_k < s_k.shift(1)
    buy_signal = ((s_k <= 2.5) & s_k_up) | (bullish_div & s_k_up) | (s_k <= 0.2)
    sell_signal = ((s_k >= 8) & s_k_down) | (bearish_div & s_k_down) | ((s_k >= 8) & (macd_line < signal_line)) | (s_k >= 9.5)
    return buy_signal.fillna(False), sell_signal.fillna(False)


def latest_signal(buy_signal: pd.Series, sell_signal: pd.Series) -> tuple[str, str | None]:
    buy_dates = list(buy_signal[buy_signal].index)
    sell_dates = list(sell_signal[sell_signal].index)
    last_buy = buy_dates[-1] if buy_dates else None
    last_sell = sell_dates[-1] if sell_dates else None
    if last_buy is None and last_sell is None:
        return "HOLD", None
    if last_sell is None or (last_buy is not None and last_buy > last_sell):
        return "BUY", str(pd.Timestamp(last_buy).date())
    return "SELL", str(pd.Timestamp(last_sell).date())
