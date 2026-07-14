from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yfinance as yf

from jp_radar.indicators import process_daily, resample_to_weekly


@dataclass(frozen=True)
class RadarDataBundle:
    daily_prices: pd.DataFrame
    weekly_prices: pd.DataFrame
    weights: dict[str, float]
    benchmark_daily: pd.DataFrame
    benchmark_weekly: pd.DataFrame


class YFinanceRadarSource:
    def __init__(self, cache_dir: str | Path = "cache/jp_radar", period: str = "5y") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.period = period

    def load(self, sector_code: str, tickers: tuple[str, ...], benchmark: str, refresh: bool = False) -> RadarDataBundle:
        daily_file = self.cache_dir / f"{sector_code}_daily.csv"
        weekly_file = self.cache_dir / f"{sector_code}_weekly.csv"
        weights_file = self.cache_dir / f"{sector_code}_weights.csv"
        bench_daily_file = self.cache_dir / f"{sector_code}_benchmark_daily.csv"
        bench_weekly_file = self.cache_dir / f"{sector_code}_benchmark_weekly.csv"

        if not refresh and daily_file.exists() and weekly_file.exists() and weights_file.exists():
            daily = pd.read_csv(daily_file, index_col=0, parse_dates=True)
            weekly = pd.read_csv(weekly_file, index_col=0, parse_dates=True)
            weights_df = pd.read_csv(weights_file)
            weights = dict(zip(weights_df["ticker"], weights_df["weight"]))
            if set(weights) != set(tickers):
                daily, weekly, weights = self._download_universe(tickers)
                daily.to_csv(daily_file)
                weekly.to_csv(weekly_file)
                pd.DataFrame([{"ticker": k, "weight": v} for k, v in weights.items()]).to_csv(weights_file, index=False)
        else:
            daily, weekly, weights = self._download_universe(tickers)
            daily.to_csv(daily_file)
            weekly.to_csv(weekly_file)
            pd.DataFrame([{"ticker": k, "weight": v} for k, v in weights.items()]).to_csv(weights_file, index=False)

        bench_cache_valid = False
        if not refresh and bench_daily_file.exists() and bench_weekly_file.exists():
            bench_daily = pd.read_csv(bench_daily_file, index_col=0, parse_dates=True)
            bench_weekly = pd.read_csv(bench_weekly_file, index_col=0, parse_dates=True)
            bench_cache_valid = {"Open", "High", "Low", "Close", "Volume"}.issubset(bench_daily.columns)
        else:
            bench_daily = pd.DataFrame()
            bench_weekly = pd.DataFrame()

        if not bench_cache_valid:
            bench_daily, bench_weekly = self._download_benchmark(benchmark)
            if bench_daily.empty:
                combined_daily = (daily * pd.Series(weights)).sum(axis=1)
                combined_weekly = (weekly * pd.Series(weights)).sum(axis=1)
                bench_daily = pd.DataFrame({"Open": combined_daily, "High": combined_daily, "Low": combined_daily, "Close": combined_daily, "Volume": 0.0})
                bench_weekly = pd.DataFrame({"Open": combined_weekly, "High": combined_weekly, "Low": combined_weekly, "Close": combined_weekly, "Volume": 0.0})
            bench_daily.to_csv(bench_daily_file)
            bench_weekly.to_csv(bench_weekly_file)

        return RadarDataBundle(daily, weekly, weights, bench_daily, bench_weekly)

    def _download_universe(self, tickers: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
        all_daily: dict[str, pd.Series] = {}
        all_weekly: dict[str, pd.Series] = {}
        caps: dict[str, float] = {}

        def fetch(ticker_text: str) -> tuple[str, pd.Series | None, pd.Series | None, float]:
            try:
                ticker = yf.Ticker(ticker_text)
                df = ticker.history(period=self.period, interval="1d")
                cap = float(ticker.info.get("marketCap", 1) or 1)
                if df.empty:
                    return ticker_text, None, None, 0.0
                daily_frame = process_daily(df)
                daily = daily_frame["Close"]
                weekly = resample_to_weekly(daily_frame)["Close"]
                return ticker_text, daily, weekly, cap
            except Exception:
                return ticker_text, None, None, 0.0

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch, ticker) for ticker in tickers]
            for future in concurrent.futures.as_completed(futures):
                ticker, daily, weekly, cap = future.result()
                if daily is not None and weekly is not None and cap > 0:
                    all_daily[ticker] = daily
                    all_weekly[ticker] = weekly
                    caps[ticker] = cap

        daily_df = pd.DataFrame(all_daily)
        weekly_df = pd.DataFrame(all_weekly)
        total_cap = sum(caps.values()) or 1.0
        weights = {ticker: cap / total_cap for ticker, cap in caps.items() if ticker in daily_df.columns}
        return daily_df, weekly_df, weights

    def _download_benchmark(self, benchmark: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        try:
            df = yf.Ticker(benchmark).history(period=self.period, interval="1d")
            if df.empty:
                return pd.DataFrame(), pd.DataFrame()
            daily = process_daily(df)
            weekly = daily.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
            columns = ["Open", "High", "Low", "Close", "Volume"]
            return daily[columns], weekly[columns]
        except Exception:
            return pd.DataFrame(), pd.DataFrame()
