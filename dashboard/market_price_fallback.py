from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

LOGGER = logging.getLogger(__name__)


def _normalize_ohlcv(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    normalized = frame.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        normalized.columns = [str(column[0]) for column in normalized.columns]
    normalized = normalized.reset_index()
    rename_map = {
        "Date": "Date",
        "Datetime": "Date",
        "index": "Date",
        "date": "Date",
        "trade_date": "Date",
        "Open": "Open",
        "open": "Open",
        "High": "High",
        "high": "High",
        "Low": "Low",
        "low": "Low",
        "Close": "Close",
        "close": "Close",
        "Adj Close": "Adj Close",
        "Volume": "Volume",
        "volume": "Volume",
    }
    normalized = normalized.rename(columns={key: value for key, value in rename_map.items() if key in normalized.columns})
    if "Date" not in normalized.columns:
        return pd.DataFrame()
    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column not in normalized.columns:
            return pd.DataFrame()
    normalized["Date"] = pd.to_datetime(normalized["Date"], errors="coerce")
    for column in ("Open", "High", "Low", "Close", "Volume"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized.dropna(subset=["Date", "Open", "High", "Low", "Close"])
    normalized = normalized.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    return normalized[["Date", "Open", "High", "Low", "Close", "Volume"]].tail(180).reset_index(drop=True)


def _load_fdr(ticker: str) -> pd.DataFrame:
    import FinanceDataReader as fdr

    start = (datetime.now(timezone.utc) - timedelta(days=420)).date().isoformat()
    return _normalize_ohlcv(fdr.DataReader(ticker, start))


def _load_yfinance(ticker: str, market: str) -> pd.DataFrame:
    import yfinance as yf

    symbol = ticker
    if market == "kr" and ticker.isdigit():
        symbol = f"{ticker.zfill(6)}.KS"
    frame = yf.download(symbol, period="18mo", interval="1d", auto_adjust=False, progress=False, threads=False)
    if frame.empty and market == "kr" and ticker.isdigit():
        symbol = f"{ticker.zfill(6)}.KQ"
        frame = yf.download(symbol, period="18mo", interval="1d", auto_adjust=False, progress=False, threads=False)
    return _normalize_ohlcv(frame)


def load_external_daily_bars(market: str, ticker: str) -> tuple[pd.DataFrame, str, str | None]:
    normalized_ticker = str(ticker or "").strip().upper()
    if market == "kr" and normalized_ticker.isdigit():
        normalized_ticker = normalized_ticker.zfill(6)

    loaders: list[tuple[str, Any]] = []
    if market == "kr":
        loaders.append(("FinanceDataReader", lambda: _load_fdr(normalized_ticker)))
    loaders.append(("yfinance", lambda: _load_yfinance(normalized_ticker, market)))

    errors: list[str] = []
    for source, loader in loaders:
        try:
            frame = loader()
        except Exception as exc:
            LOGGER.warning("External OHLCV fallback failed: source=%s ticker=%s error=%s", source, normalized_ticker, exc)
            errors.append(f"{source}: {exc}")
            continue
        if not frame.empty:
            return frame, source, None
        errors.append(f"{source}: empty")
    return pd.DataFrame(), "외부 데이터 없음", " | ".join(errors) if errors else None
