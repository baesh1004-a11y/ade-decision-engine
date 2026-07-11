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

    frame = daily_ohlc[["Open", "High", "Low", "Close"]].copy()
    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index().dropna(subset=["Open", "Close"])
    if frame.empty:
        raise ValueError("No OHLC data available for yearly meaning")

    latest_data_year = int(frame.index.max().year)
    completed_years = sorted({int(year) for year in frame.index.year if int(year) < latest_data_year})
    meaning_year = completed_years[-1] if completed_years else latest_data_year
    year_frame = frame[frame.index.year == meaning_year]
    if year_frame.empty:
        raise ValueError(f"No OHLC data for year {meaning_year}")

    yearly_open = float(year_frame["Open"].iloc[0])
    yearly_high = float(year_frame["High"].max())
    yearly_low = float(year_frame["Low"].min())
    yearly_close = float(year_frame["Close"].iloc[-1])
    latest_close = float(frame["Close"].iloc[-1])
    current = float(current_price) if current_price is not None else latest_close
    bullish = yearly_close >= yearly_open

    state = _state(
        current=current,
        yearly_open=yearly_open,
        yearly_close=yearly_close,
        bullish=bullish,
        tolerance_pct=tolerance_pct,
    )

    return YearlyMeaning(
        year=meaning_year,
        open=yearly_open,
        high=yearly_high,
        low=yearly_low,
        close=yearly_close,
        current=current,
        bullish=bullish,
        state=state,
        distance_open=_distance_pct(current, yearly_open),
        distance_close=_distance_pct(current, yearly_close) if bullish else None,
    )


def with_current_price(
    meaning: YearlyMeaning,
    current_price: float,
    tolerance_pct: float = 0.15,
) -> YearlyMeaning:
    current = float(current_price)
    state = _state(
        current=current,
        yearly_open=meaning.open,
        yearly_close=meaning.close,
        bullish=meaning.bullish,
        tolerance_pct=tolerance_pct,
    )
    return replace(
        meaning,
        current=current,
        state=state,
        distance_open=_distance_pct(current, meaning.open),
        distance_close=_distance_pct(current, meaning.close) if meaning.bullish else None,
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
    if bullish:
        if _near(current, yearly_close, tolerance_pct):
            return "AT_CLOSE"
        if current > yearly_close:
            return "ABOVE_CLOSE"
        if yearly_open < current < yearly_close:
            return "BETWEEN"
        if current < yearly_open:
            return "BELOW_OPEN"
        return "ABOVE_OPEN"
    if current > yearly_open:
        return "ABOVE_OPEN"
    return "BELOW_OPEN"


def _near(value: float, reference: float, tolerance_pct: float) -> bool:
    if reference == 0:
        return False
    return abs(value / reference - 1.0) * 100.0 <= tolerance_pct


def _distance_pct(value: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return (value / reference - 1.0) * 100.0
