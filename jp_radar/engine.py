from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from jp_radar.datasource import YFinanceRadarSource
from jp_radar.indicators import calculate_signals, composite_energy, graded_signal, latest_signal, macd
from jp_radar.sectors import RadarSector, get_sector
from jp_radar.yearly_meaning import YearlyMeaning, calculate_yearly_meaning
from jp_radar.yearly_score import calculate_yearly_score


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
    signal_grade: str
    latest_energy: float


@dataclass(frozen=True)
class RadarResult:
    sector: RadarSector
    daily: TimeframeRadarResult
    weekly: TimeframeRadarResult
    yearly: YearlyMeaning
    yearly_score: float
    weights: dict[str, float]

    @property
    def combined_signal(self) -> str:
        if self.weekly.latest_signal == "BUY" and self.daily.latest_signal == "BUY":
            return "STRONG BUY"
        if self.weekly.latest_signal == "BUY" and self.daily.latest_signal != "SELL":
            return "BUY"
        if self.weekly.latest_signal == "SELL" and self.daily.latest_signal == "SELL":
            return "STRONG SELL"
        if self.weekly.latest_signal == "SELL" or self.daily.latest_signal == "SELL":
            return "SELL"
        if self.weekly.latest_energy <= 2.5 or self.daily.latest_energy <= 2.5:
            return "WATCH BUY"
        if self.weekly.latest_energy >= 8.0 or self.daily.latest_energy >= 8.0:
            return "WATCH SELL"
        return "HOLD"


class JPRadarEngine:
    def __init__(self, source: YFinanceRadarSource | None = None) -> None:
        self.source = source or YFinanceRadarSource()

    def analyze(self, sector_code: str = "kospi50", refresh: bool = False) -> RadarResult:
        sector = get_sector(sector_code)
        bundle = self.source.load(sector.code, sector.tickers, sector.benchmark, refresh=refresh)
        daily_index = self._weighted_index(bundle.daily_prices, bundle.weights)
        weekly_index = self._weighted_index(bundle.weekly_prices, bundle.weights)
        daily = self._analyze_timeframe(daily_index, bundle.benchmark_daily["Close"], is_daily=True)
        weekly = self._analyze_timeframe(weekly_index, bundle.benchmark_weekly["Close"], is_daily=False)
        yearly = calculate_yearly_meaning(bundle.benchmark_daily)
        yearly_score = calculate_yearly_score(yearly)
        return RadarResult(
            sector=sector,
            daily=daily,
            weekly=weekly,
            yearly=yearly,
            yearly_score=yearly_score,
            weights=bundle.weights,
        )

    @staticmethod
    def _weighted_index(price_frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
        weight_series = pd.Series(weights)
        aligned = price_frame[[c for c in price_frame.columns if c in weight_series.index]]
        return (aligned * weight_series).sum(axis=1).dropna()

    @staticmethod
    def _analyze_timeframe(index_series: pd.Series, benchmark: pd.Series, is_daily: bool) -> TimeframeRadarResult:
        s_k, s_d = composite_energy(index_series, 5, 3, 3)
        m_k, m_d = composite_energy(index_series, 10, 6, 6)
        l_k, l_d = composite_energy(index_series, 20, 12, 12)
        macd_line, signal_line = macd(index_series)
        buy, sell = calculate_signals(index_series, macd_line, signal_line, s_k, is_daily=is_daily)
        signal_text, signal_date = latest_signal(buy, sell)
        latest_energy = float(s_k.iloc[-1]) if not s_k.empty else 0.0
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
            signal_grade=graded_signal(signal_text, latest_energy),
            latest_energy=latest_energy,
        )
