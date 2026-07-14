from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pandas as pd
import yfinance as yf

from jp_radar.advanced import analyze_120m, calculate_meaningful_lines, resample_to_120m
from jp_radar.engine import JPRadarEngine, RadarResult
from jp_radar.indicators import macd, process_daily, resample_to_weekly
from jp_radar.live_engine import IntradayRadarResult, JPRadarLiveEngine
from jp_radar.sectors import RadarSector
from jp_radar.yearly_meaning import calculate_yearly_meaning, with_current_price
from jp_radar.yearly_score import calculate_yearly_score


class JPStockRadarEngine:
    """Run the same JP Radar rules against one individual stock."""

    def analyze(
        self,
        ticker: str,
        *,
        period: str = "5y",
        intraday_period: str = "1y",
        intraday_interval: str = "60m",
    ) -> IntradayRadarResult:
        symbol = normalize_ticker(ticker)
        daily_raw = yf.Ticker(symbol).history(period=period, interval="1d")
        if daily_raw.empty:
            raise ValueError(f"가격 데이터를 찾을 수 없습니다: {symbol}")

        daily_frame = process_daily(daily_raw)
        weekly_frame = resample_to_weekly(daily_frame)
        daily_close = pd.to_numeric(daily_frame["Close"], errors="coerce").dropna()
        weekly_close = pd.to_numeric(weekly_frame["Close"], errors="coerce").dropna()
        if daily_close.empty or weekly_close.empty:
            raise ValueError(f"분석 가능한 가격 데이터가 부족합니다: {symbol}")

        name = _stock_name(symbol)
        sector = RadarSector(
            code=f"stock:{symbol}", name=name, benchmark=symbol,
            benchmark_name=name, tickers=(symbol,),
        )
        daily = JPRadarEngine._analyze_timeframe(daily_close, daily_close, is_daily=True)
        weekly = JPRadarEngine._analyze_timeframe(weekly_close, weekly_close, is_daily=False)
        yearly = calculate_yearly_meaning(daily_frame[["Open", "High", "Low", "Close"]])
        radar = RadarResult(
            sector=sector, daily=daily, weekly=weekly, yearly=yearly,
            yearly_score=calculate_yearly_score(yearly), weights={symbol: 1.0},
        )

        intraday = JPRadarLiveEngine._download_intraday(symbol, intraday_period, intraday_interval)
        if intraday.empty:
            intraday_price = daily_close.tail(240)
            latest = float(intraday_price.iloc[-1])
            previous = float(intraday_price.iloc[-2]) if len(intraday_price) > 1 else latest
            source = "DAILY_FALLBACK"
        else:
            intraday_price = pd.to_numeric(intraday["Close"], errors="coerce").dropna()
            latest = float(intraday_price.iloc[-1])
            previous = JPRadarLiveEngine._previous_session_close(intraday_price)
            source = "YFINANCE_60M"

        price_120m = resample_to_120m(intraday_price)
        radar_120m = analyze_120m(price_120m if not price_120m.empty else intraday_price)
        yearly = with_current_price(radar.yearly, latest)
        radar = replace(radar, yearly=yearly, yearly_score=calculate_yearly_score(yearly))
        change_rate = 0.0 if previous <= 0 else (latest / previous - 1.0) * 100.0
        macd_line, signal_line = macd(intraday_price)
        benchmark_ohlcv = daily_frame[[c for c in ["Open", "High", "Low", "Close", "Volume"] if c in daily_frame.columns]]
        return IntradayRadarResult(
            radar=radar,
            radar_120m=radar_120m,
            intraday_price=intraday_price,
            intraday_macd=macd_line,
            intraday_signal=signal_line,
            benchmark_ohlcv=benchmark_ohlcv,
            meaningful_lines=tuple(calculate_meaningful_lines(benchmark_ohlcv)),
            latest_price=latest,
            change_rate=change_rate,
            updated_at=datetime.now().isoformat(timespec="seconds"),
            source=source,
        )


def normalize_ticker(value: str) -> str:
    text = value.strip().upper()
    if not text:
        raise ValueError("종목코드를 입력하세요.")
    if "." in text or text.startswith("^"):
        return text
    if text.isdigit() and len(text) == 6:
        return f"{text}.KS"
    return text


def _stock_name(symbol: str) -> str:
    try:
        ticker = yf.Ticker(symbol)
        name = ticker.info.get("shortName")
        return str(name or symbol)
    except Exception:
        return symbol
