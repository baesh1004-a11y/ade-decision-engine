from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from jp_radar.engine import JPRadarEngine, TimeframeRadarResult


@dataclass(frozen=True)
class MeaningfulLine:
    timeframe: str
    source_date: str
    line_type: str
    price: float
    trading_value: float


def resample_to_120m(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    out = series.resample("2h").last().dropna()
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out


def analyze_120m(index_series: pd.Series) -> TimeframeRadarResult:
    return JPRadarEngine._analyze_timeframe(index_series, index_series, is_daily=True)


def calculate_meaningful_lines(daily_ohlcv: pd.DataFrame, top_n: int = 4) -> list[MeaningfulLine]:
    required = {"Open", "Close", "Volume"}
    if daily_ohlcv.empty or not required.issubset(daily_ohlcv.columns):
        return []

    frame = daily_ohlcv.copy()
    frame.index = pd.to_datetime(frame.index)
    for column in ["Open", "Close", "Volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["Open", "Close", "Volume"]).sort_index()
    frame["TradingValue"] = frame["Volume"] * frame["Close"]

    specs = [("W", "W-FRI"), ("M", "ME"), ("Y", "YE")]
    result: list[MeaningfulLine] = []
    seen: set[tuple[str, int]] = set()

    for timeframe, rule in specs:
        try:
            sampled = frame.resample(rule).agg(
                Open=("Open", "first"),
                Close=("Close", "last"),
                TradingValue=("TradingValue", "sum"),
            ).dropna()
        except ValueError:
            legacy = {"ME": "M", "YE": "Y"}.get(rule, rule)
            sampled = frame.resample(legacy).agg(
                Open=("Open", "first"),
                Close=("Close", "last"),
                TradingValue=("TradingValue", "sum"),
            ).dropna()

        for stamp, row in sampled.nlargest(top_n, "TradingValue").iterrows():
            open_price = float(row["Open"])
            close_price = float(row["Close"])
            values = [("OPEN", open_price)]
            if close_price > open_price:
                values.extend([("MID", (open_price + close_price) / 2.0), ("CLOSE", close_price)])
            for line_type, price in values:
                key = (timeframe, int(round(price * 100)))
                if key in seen:
                    continue
                seen.add(key)
                result.append(
                    MeaningfulLine(
                        timeframe=timeframe,
                        source_date=str(pd.Timestamp(stamp).date()),
                        line_type=line_type,
                        price=round(price, 4),
                        trading_value=float(row["TradingValue"]),
                    )
                )
    return sorted(result, key=lambda item: (item.timeframe, item.price))
