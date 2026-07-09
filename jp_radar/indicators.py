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


def composite_energy(series: pd.Series, period: int, smooth_k: int, smooth_d: int) -> tuple[pd.Series, pd.Series]:
    """RSI + Stochastic composite energy scaled to 0~10."""
    low = series.rolling(window=period, min_periods=1).min()
    high = series.rolling(window=period, min_periods=1).max()
    fast_k = 100.0 * ((series - low) / (high - low + 1e-9))

    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=1, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=1, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    composite_raw = (fast_k + rsi) / 2.0
    k = composite_raw.ewm(span=smooth_k, adjust=False).mean() / 10.0
    d = k.ewm(span=smooth_d, adjust=False).mean()
    return k, d


# Backward-compatible alias. JP Radar now uses composite energy by default.
stochastic_energy = composite_energy


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series]:
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def calculate_signals(
    index_series: pd.Series,
    macd_line: pd.Series,
    signal_line: pd.Series,
    s_k: pd.Series,
    is_daily: bool = True,
) -> tuple[pd.Series, pd.Series]:
    div_window = 10
    price_diff = index_series - index_series.shift(div_window)
    macd_diff = macd_line - macd_line.shift(div_window)
    bullish_div = (price_diff <= 0) & (macd_diff >= 0)
    bearish_div = (price_diff >= 0) & (macd_diff <= 0)
    s_k_up = s_k > s_k.shift(1)
    s_k_down = s_k < s_k.shift(1)

    if is_daily:
        buy_signal = ((s_k <= 2.5) & s_k_up) | (bullish_div & s_k_up) | (s_k <= 0.2)
        sell_signal = ((s_k >= 8) & s_k_down) | (bearish_div & s_k_down) | ((s_k >= 8) & (macd_line < signal_line)) | (s_k >= 9.5)
    else:
        buy_signal = ((s_k <= 2) & s_k_up) | (bullish_div & s_k_up)
        sell_signal = ((s_k >= 8.5) & s_k_down) | (bearish_div & s_k_down)
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


def graded_signal(timeframe_signal: str, energy: float) -> str:
    if timeframe_signal == "BUY" and energy <= 1.0:
        return "STRONG BUY"
    if timeframe_signal == "SELL" and energy >= 9.0:
        return "STRONG SELL"
    if timeframe_signal in {"BUY", "SELL"}:
        return timeframe_signal
    if energy <= 2.5:
        return "WATCH BUY"
    if energy >= 8.0:
        return "WATCH SELL"
    return "HOLD"
