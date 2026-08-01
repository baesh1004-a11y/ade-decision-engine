from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class MarketMetric:
    label: str
    value: float | None
    change: float | None
    change_rate: float | None
    updated_at: float | None
    status: str
    source: str
    error: str | None = None


_SYMBOLS: dict[str, tuple[str, str]] = {
    "kospi": ("KOSPI", "^KS11"),
    "kosdaq": ("KOSDAQ", "^KQ11"),
    "sp500": ("S&P 500", "^GSPC"),
    "nasdaq": ("NASDAQ", "^IXIC"),
    "usdkrw": ("USD/KRW", "KRW=X"),
    "vix": ("VIX", "^VIX"),
}
_CACHE_LOCK = RLock()
_CACHE: tuple[float, dict[str, MarketMetric], str | None] | None = None
_CACHE_TTL_SECONDS = 45.0


def _history_metric(label: str, symbol: str, history: pd.DataFrame, now: float) -> MarketMetric:
    if history.empty or "Close" not in history:
        return MarketMetric(label, None, None, None, None, "오류", "Yahoo Finance", "가격 데이터 없음")
    closes = history["Close"].dropna()
    if closes.empty:
        return MarketMetric(label, None, None, None, None, "오류", "Yahoo Finance", "종가 데이터 없음")
    value = float(closes.iloc[-1])
    previous = float(closes.iloc[-2]) if len(closes) >= 2 else value
    change = value - previous
    change_rate = change / previous * 100 if previous else 0.0
    status = "정상" if now - time.time() < 90 else "지연"
    return MarketMetric(label, value, change, change_rate, now, status, "Yahoo Finance")


def load_market_overview(*, refresh: bool = False) -> tuple[dict[str, MarketMetric], str | None]:
    global _CACHE
    now = time.time()
    with _CACHE_LOCK:
        if not refresh and _CACHE and now - _CACHE[0] <= _CACHE_TTL_SECONDS:
            return _CACHE[1], _CACHE[2]
    symbols = [item[1] for item in _SYMBOLS.values()]
    try:
        frame = yf.download(
            tickers=" ".join(symbols),
            period="5d",
            interval="1m",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
            timeout=15,
        )
        metrics: dict[str, MarketMetric] = {}
        for key, (label, symbol) in _SYMBOLS.items():
            if isinstance(frame.columns, pd.MultiIndex):
                history = frame[symbol] if symbol in frame.columns.get_level_values(0) else pd.DataFrame()
            else:
                history = frame
            metrics[key] = _history_metric(label, symbol, history, now)
        error = None if any(item.value is not None for item in metrics.values()) else "시장 데이터 조회 결과가 없습니다."
    except Exception as exc:
        metrics = {
            key: MarketMetric(label, None, None, None, None, "오류", "Yahoo Finance", str(exc))
            for key, (label, _symbol) in _SYMBOLS.items()
        }
        error = str(exc)
    with _CACHE_LOCK:
        _CACHE = (time.time(), metrics, error)
    return metrics, error


def database_health(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        return {"status": "오류", "detail": "DB 파일 없음", "checked_at": time.time()}
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3) as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "정상", "detail": str(path), "checked_at": time.time()}
    except Exception as exc:
        return {"status": "오류", "detail": str(exc), "checked_at": time.time()}


def market_health(metrics: dict[str, MarketMetric], error: str | None) -> dict[str, Any]:
    valid = [item for item in metrics.values() if item.value is not None and item.updated_at]
    latest = max((item.updated_at or 0 for item in valid), default=None)
    if valid:
        return {"status": "정상", "detail": f"{len(valid)}/{len(metrics)} 지표 수신", "checked_at": latest, "error": error}
    return {"status": "오류", "detail": error or "수신 데이터 없음", "checked_at": None, "error": error}


def load_sector_strength(db_path: str | Path, *, limit: int = 5) -> tuple[list[dict[str, Any]], str | None]:
    path = Path(db_path)
    if not path.exists():
        return [], "시장 DB 파일이 없습니다."
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "sector_strength" in tables:
                rows = conn.execute(
                    "SELECT sector, change_rate, breadth, relative_strength FROM sector_strength ORDER BY relative_strength DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(row) for row in rows], None
        return [], "섹터 강도 계산 데이터가 아직 없습니다."
    except Exception as exc:
        return [], str(exc)
