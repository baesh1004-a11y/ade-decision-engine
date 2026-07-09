from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from jp_radar.datasource import RadarDataBundle, YFinanceRadarSource
from jp_radar.indicators import calculate_signals, latest_signal, macd, stochastic_energy
from jp_radar.sectors import RadarSector, get_sector


@dataclass(frozen=True)
class TimeframeRadarResult:
    index: pd.Series
    benchmark: pd.Series
    s_k: pd.Series
    s_d: pd.Series
    m_k: pd.Series
    m_d: pd.Series
    l_k: pd.Series
    l_d: pd.Series
    macd: pd.Series
    signal: pd.Series
    buy_signal: pd.Series
    sell_signal: pd.Series
    latest_signal: str
    latest_signal_date: str | None
    latest_energy: float


@dataclass(frozen=True)
class RadarResult:
    sector: RadarSector
    daily: TimeframeRadarResult
    weekly: TimeframeRadarResult
    weights: dict[str, float]

    @property
    def combined_signal(self) -> str:
        if self.weekly.latest_signal == "BUY" and self.daily.latest_signal != "SELL":
            return "BUY"
        if self.weekly.latest_signal == "SELL" or self.daily.latest_signal == "SELL":
            return "SELL"
        return "HOLD"


class JPRadarEngine:
    def __init__(self, source: YFinanceRadarSource | None = None) -> None:
        self.source = source or YFinanceRadarSource()

    def analyze(self, sector_code: str = "kosdaq50", refresh: bool = False) -> RadarResult:
        sector = get_sector(sector_code)
        bundle = self.source.load(sector.code, sector.tickers, sector.benchmark, refresh=refresh)
        daily_index = self._weighted_index(bundle.daily_prices, bundle.weights)
        weekly_index = self._weighted_index(bundle.weekly_prices, bundle.weights)
        daily = self._analyze_timeframe(daily_index, bundle.benchmark_daily["Close"])
        weekly = self._analyze_timeframe(weekly_index, bundle.benchmark_weekly["Close"])
        return RadarResult(sector=sector, daily=daily, weekly=weekly, weights=bundle.weights)

    @staticmethod
    def _weighted_index(price_frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
        weight_series = pd.Series(weights)
        aligned = price_frame[[c for c in price_frame.columns if c in weight_series.index]]
        return (aligned * weight_series).sum(axis=1).dropna()

    @staticmethod
    def _analyze_timeframe(index_series: pd.Series, benchmark: pd.Series) -> TimeframeRadarResult:
        s_k, s_d = stochastic_energy(index_series, 5, 3, 3)
        m_k, m_d = stochastic_energy(index_series, 10, 6, 6)
        l_k, l_d = stochastic_energy(index_series, 20, 12, 12)
        macd_line, signal_line = macd(index_series)
        buy, sell = calculate_signals(index_series, macd_line, signal_line, s_k)
        signal_text, signal_date = latest_signal(buy, sell)
        return TimeframeRadarResult(
            index=index_series,
            benchmark=benchmark,
            s_k=s_k,
            s_d=s_d,
            m_k=m_k,
            m_d=m_d,
            l_k=l_k,
            l_d=l_d,
            macd=macd_line,
            signal=signal_line,
            buy_signal=buy,
            sell_signal=sell,
            latest_signal=signal_text,
            latest_signal_date=signal_date,
            latest_energy=float(s_k.iloc[-1]) if not s_k.empty else 0.0,
        )
