from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

import pandas as pd
import yfinance as yf

from jp_radar.advanced import MeaningfulLine, analyze_120m, calculate_meaningful_lines, resample_to_120m
from jp_radar.engine import JPRadarEngine, RadarResult, TimeframeRadarResult
from jp_radar.indicators import macd
from jp_radar.yearly_meaning import with_current_price
from jp_radar.yearly_score import calculate_yearly_score


@dataclass(frozen=True)
class IntradayRadarResult:
    radar: RadarResult
    radar_120m: TimeframeRadarResult
    intraday_price: pd.Series
    intraday_macd: pd.Series
    intraday_signal: pd.Series
    benchmark_ohlcv: pd.DataFrame
    meaningful_lines: tuple[MeaningfulLine, ...]
    latest_price: float
    change_rate: float
    updated_at: str
    source: str


class JPRadarLiveEngine:
    """Combine daily/weekly JP Radar with 120-minute timing and benchmark overlays."""

    def __init__(self) -> None:
        self.radar_engine = JPRadarEngine()

    def analyze(
        self,
        sector_code: str = "kospi50",
        refresh_history: bool = False,
        intraday_period: str = "1y",
        intraday_interval: str = "60m",
    ) -> IntradayRadarResult:
        radar = self.radar_engine.analyze(sector_code, refresh=refresh_history)
        intraday = self._download_intraday(radar.sector.benchmark, intraday_period, intraday_interval)
        benchmark_daily = self._download_daily_ohlcv(radar.sector.benchmark, period="5y")

        if intraday.empty:
            price = radar.daily.benchmark.dropna()
            latest = float(price.iloc[-1]) if not price.empty else 0.0
            previous = float(price.iloc[-2]) if len(price) > 1 else latest
            intraday_price = price.tail(240)
            source = "DAILY_FALLBACK"
        else:
            intraday_price = pd.to_numeric(intraday["Close"], errors="coerce").dropna()
            latest = float(intraday_price.iloc[-1]) if not intraday_price.empty else 0.0
            previous = self._previous_session_close(intraday_price)
            source = "YFINANCE_60M"

        price_120m = resample_to_120m(intraday_price)
        if price_120m.empty:
            price_120m = intraday_price
        radar_120m = analyze_120m(price_120m)

        if latest > 0:
            yearly = with_current_price(radar.yearly, latest)
            radar = replace(radar, yearly=yearly, yearly_score=calculate_yearly_score(yearly))

        change_rate = 0.0 if previous <= 0 else (latest / previous - 1.0) * 100.0
        macd_line, signal_line = macd(intraday_price)
        meaningful = tuple(calculate_meaningful_lines(benchmark_daily))
        return IntradayRadarResult(
            radar=radar,
            radar_120m=radar_120m,
            intraday_price=intraday_price,
            intraday_macd=macd_line,
            intraday_signal=signal_line,
            benchmark_ohlcv=benchmark_daily,
            meaningful_lines=meaningful,
            latest_price=latest,
            change_rate=change_rate,
            updated_at=datetime.now().isoformat(timespec="seconds"),
            source=source,
        )

    @staticmethod
    def _download_intraday(symbol: str, period: str, interval: str) -> pd.DataFrame:
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval)
            if df.empty:
                return pd.DataFrame()
            out = df.copy()
            if getattr(out.index, "tz", None) is not None:
                out.index = out.index.tz_localize(None)
            return out.dropna(subset=["Close"])
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _download_daily_ohlcv(symbol: str, period: str = "5y") -> pd.DataFrame:
        try:
            df = yf.Ticker(symbol).history(period=period, interval="1d")
            if df.empty:
                return pd.DataFrame()
            out = df.copy()
            if getattr(out.index, "tz", None) is not None:
                out.index = out.index.tz_localize(None)
            columns = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in out.columns]
            return out[columns].dropna(subset=["Open", "Close"])
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _previous_session_close(series: pd.Series) -> float:
        if series.empty:
            return 0.0
        grouped = series.groupby(series.index.date)
        closes = grouped.last()
        if len(closes) >= 2:
            return float(closes.iloc[-2])
        return float(series.iloc[0])
