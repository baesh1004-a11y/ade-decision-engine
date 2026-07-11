from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd


@dataclass(frozen=True)
class YearlyMeaning:
    year: int
    open: float
    high: float
    low: float
    close: float
    current: float
    bullish: bool
    state: str
    distance_open: float
    distance_close: float | None

    @property
    def show_close_line(self) -> bool:
        return self.bullish


def calculate_yearly_meaning(
    daily_ohlc: pd.DataFrame,
    current_price: float | None = None,
    tolerance_pct: float = 0.15,
) -> YearlyMeaning:
    required = {"Open", "High", "Low", "Close"}
    missing = required.difference(daily_ohlc.columns)
    if missing:
        raise ValueError(f"Yearly meaning requires OHLC columns: {sorted(missing)}")

    frame = daily_ohlc[list(required)].copy()
    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index().dropna(subset=["Open", "Close"])
    if frame.empty:
        raise ValueError("No OHLC data available for yearly meaning")

    latest_year = int(frame.index.max().year)
    year_frame = frame[frame.index.year == latest_year]
    if year_frame.empty:
        raise ValueError(f"No OHLC data for year {latest_year}")

    yearly_open = float(year_frame["Open"].iloc[0])
    yearly_high = float(year_frame["High"].max())
    yearly_low = float(year_frame["Low"].min())
    yearly_close = float(year_frame["Close"].iloc[-1])
    current = float(current_price) if current_price is not None else yearly_close
    bullish = current >= yearly_open

    state = _state(
        current=current,
        yearly_open=yearly_open,
        yearly_close=current if current_price is not None else yearly_close,
        bullish=bullish,
        tolerance_pct=tolerance_pct,
    )
    distance_open = _distance_pct(current, yearly_open)
    distance_close = _distance_pct(current, yearly_close) if bullish else None

    return YearlyMeaning(
        year=latest_year,
        open=yearly_open,
        high=yearly_high,
        low=yearly_low,
        close=yearly_close,
        current=current,
        bullish=bullish,
        state=state,
        distance_open=distance_open,
        distance_close=distance_close,
    )


def with_current_price(
    meaning: YearlyMeaning,
    current_price: float,
    tolerance_pct: float = 0.15,
) -> YearlyMeaning:
    current = float(current_price)
    bullish = current >= meaning.open
    state = _state(
        current=current,
        yearly_open=meaning.open,
        yearly_close=current,
        bullish=bullish,
        tolerance_pct=tolerance_pct,
    )
    return replace(
        meaning,
        close=current,
        current=current,
        bullish=bullish,
        state=state,
        distance_open=_distance_pct(current, meaning.open),
        distance_close=0.0 if bullish else None,
    )


def _state(
    current: float,
    yearly_open: float,
    yearly_close: float,
    bullish: bool,
    tolerance_pct: float,
) -> str:
    if _near(current, yearly_open, tolerance_pct):
        return "AT_OPEN"
    if not bullish:
        return "BELOW_OPEN"
    if _near(current, yearly_close, tolerance_pct):
        return "AT_CLOSE"
    if current > yearly_close:
        return "ABOVE_CLOSE"
    if yearly_open < current < yearly_close:
        return "BETWEEN"
    return "ABOVE_OPEN"


def _near(value: float, reference: float, tolerance_pct: float) -> bool:
    if reference == 0:
        return False
    return abs(value / reference - 1.0) * 100.0 <= tolerance_pct


def _distance_pct(value: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return (value / reference - 1.0) * 100.0
