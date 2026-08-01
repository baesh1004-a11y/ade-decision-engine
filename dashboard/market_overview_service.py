from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, replace
from datetime import datetime, time as dt_time, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

try:
    from pykrx import stock as pykrx_stock
except Exception:  # pragma: no cover
    pykrx_stock = None


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
    fetched_at: float | None = None
    market_state: str = "unknown"
    verified: bool = False


_SYMBOLS: dict[str, tuple[str, str]] = {
    "kospi": ("KOSPI", "^KS11"),
    "kosdaq": ("KOSDAQ", "^KQ11"),
    "sp500": ("S&P 500", "^GSPC"),
    "nasdaq": ("NASDAQ", "^IXIC"),
    "usdkrw": ("USD/KRW", "KRW=X"),
    "vix": ("VIX", "^VIX"),
}
_MARKET_META: dict[str, tuple[str, dt_time, dt_time]] = {
    "^KS11": ("Asia/Seoul", dt_time(9, 0), dt_time(15, 30)),
    "^KQ11": ("Asia/Seoul", dt_time(9, 0), dt_time(15, 30)),
    "^GSPC": ("America/New_York", dt_time(9, 30), dt_time(16, 0)),
    "^IXIC": ("America/New_York", dt_time(9, 30), dt_time(16, 0)),
    "^VIX": ("America/Chicago", dt_time(8, 30), dt_time(15, 15)),
    "KRW=X": ("Etc/UTC", dt_time(0, 0), dt_time(23, 59)),
}
_VALUE_RANGES: dict[str, tuple[float, float]] = {
    "^KS11": (500.0, 5000.0),
    "^KQ11": (200.0, 2500.0),
    "^GSPC": (1000.0, 15000.0),
    "^IXIC": (3000.0, 50000.0),
    "KRW=X": (500.0, 3000.0),
    "^VIX": (5.0, 200.0),
}
_CACHE_LOCK = RLock()
_CACHE: tuple[float, dict[str, MarketMetric], str | None] | None = None
_CACHE_TTL_SECONDS = 45.0
_STALE_TTL_SECONDS = 15 * 60.0
_FAILURE_BACKOFF_SECONDS = 20.0
_NEXT_REFRESH_AT = 0.0
_CALL_COUNT = 0
_LAST_ATTEMPT_AT: float | None = None
_LAST_SUCCESS_AT: float | None = None
_LAST_ERROR: str | None = None
_SECTOR_CACHE: tuple[float, list[dict[str, Any]], str | None] | None = None
_SECTOR_CACHE_TTL_SECONDS = 300.0


def _market_state(symbol: str, now: float) -> str:
    timezone_name, open_at, close_at = _MARKET_META.get(symbol, ("Etc/UTC", dt_time(0, 0), dt_time(23, 59)))
    local = datetime.fromtimestamp(now, tz=timezone.utc).astimezone(ZoneInfo(timezone_name))
    if local.weekday() >= 5:
        return "휴장"
    current = local.time().replace(tzinfo=None)
    if open_at <= current <= close_at:
        return "장중"
    if current < open_at:
        return "장전"
    return "장마감"


def _last_bar_timestamp(history: pd.DataFrame, fallback: float) -> float:
    if history.empty:
        return fallback
    try:
        value = pd.Timestamp(history.index[-1])
        if value.tzinfo is None:
            value = value.tz_localize("UTC")
        else:
            value = value.tz_convert("UTC")
        return float(value.timestamp())
    except Exception:
        return fallback


def _history_metric(label: str, symbol: str, history: pd.DataFrame, now: float) -> MarketMetric:
    source = "Yahoo Finance · 참고용"
    state = _market_state(symbol, now)
    if history.empty or "Close" not in history:
        return MarketMetric(label, None, None, None, None, "오류", source, "가격 데이터 없음", now, state, False)
    closes = history["Close"].dropna()
    if closes.empty:
        return MarketMetric(label, None, None, None, None, "오류", source, "종가 데이터 없음", now, state, False)
    value = float(closes.iloc[-1])
    previous = float(closes.iloc[-2]) if len(closes) >= 2 else value
    change = value - previous
    change_rate = change / previous * 100 if previous else 0.0
    updated_at = _last_bar_timestamp(history.loc[closes.index], now)
    minimum, maximum = _VALUE_RANGES.get(symbol, (0.0, float("inf")))
    if not pd.notna(value) or not (minimum <= value <= maximum):
        return MarketMetric(label, None, None, None, updated_at, "검증 필요", source, f"값 범위 이탈: {value:,.2f}", now, state, False)
    if abs(change_rate) > 20:
        return MarketMetric(label, None, None, None, updated_at, "검증 필요", source, f"비정상 변동률 {change_rate:.2f}%", now, state, False)
    age = max(0.0, now - updated_at)
    status = "정상"
    verified = True
    if state == "장중" and age > 10 * 60:
        status = "지연"
        verified = False
    elif state in {"장마감", "휴장"}:
        status = "종가"
    elif state == "장전":
        status = "전일종가"
    return MarketMetric(label, value, change, change_rate, updated_at, status, source, None, now, state, verified)


def _stale_metrics(now: float, error: str) -> dict[str, MarketMetric] | None:
    if not _CACHE:
        return None
    _, cached_metrics, _ = _CACHE
    stale: dict[str, MarketMetric] = {}
    for key, metric in cached_metrics.items():
        if metric.value is None or not metric.updated_at:
            stale[key] = replace(metric, status="오류", error=error, fetched_at=now, verified=False)
            continue
        age = now - metric.updated_at
        if age <= _STALE_TTL_SECONDS:
            stale[key] = replace(metric, status="마지막 정상값 사용", error=error, fetched_at=now, verified=False)
        else:
            stale[key] = replace(metric, value=None, change=None, change_rate=None, status="만료", error=error, fetched_at=now, verified=False)
    return stale


def load_market_overview(*, refresh: bool = False) -> tuple[dict[str, MarketMetric], str | None]:
    global _CACHE, _NEXT_REFRESH_AT, _CALL_COUNT, _LAST_ATTEMPT_AT, _LAST_SUCCESS_AT, _LAST_ERROR
    now = time.time()
    with _CACHE_LOCK:
        if not refresh and _CACHE and now - _CACHE[0] <= _CACHE_TTL_SECONDS:
            return _CACHE[1], _CACHE[2]
        if not refresh and _CACHE and now < _NEXT_REFRESH_AT:
            return _CACHE[1], _CACHE[2]
        _CALL_COUNT += 1
        _LAST_ATTEMPT_AT = now
        symbols = [item[1] for item in _SYMBOLS.values()]
        try:
            frame = yf.download(tickers=" ".join(symbols), period="5d", interval="1m", group_by="ticker", auto_adjust=False, progress=False, threads=True, timeout=15)
            metrics: dict[str, MarketMetric] = {}
            for key, (label, symbol) in _SYMBOLS.items():
                if isinstance(frame.columns, pd.MultiIndex):
                    history = frame[symbol] if symbol in frame.columns.get_level_values(0) else pd.DataFrame()
                else:
                    history = frame
                metrics[key] = _history_metric(label, symbol, history, now)
            valid_count = sum(item.value is not None for item in metrics.values())
            verified_count = sum(item.verified for item in metrics.values())
            if valid_count == 0:
                raise RuntimeError("시장 데이터 조회 결과가 없습니다.")
            error = None
            if valid_count != len(metrics) or verified_count != len(metrics):
                error = f"시장지표 검증 결과: 값 {valid_count}/{len(metrics)}, 검증 {verified_count}/{len(metrics)}"
            _CACHE = (time.time(), metrics, error)
            _LAST_SUCCESS_AT = now
            _LAST_ERROR = error
            _NEXT_REFRESH_AT = now + _CACHE_TTL_SECONDS
            return metrics, error
        except Exception as exc:
            error = str(exc)
            _LAST_ERROR = error
            _NEXT_REFRESH_AT = now + _FAILURE_BACKOFF_SECONDS
            stale = _stale_metrics(now, error)
            if stale is not None:
                _CACHE = (_CACHE[0], stale, error)
                return stale, error
            metrics = {key: MarketMetric(label, None, None, None, None, "오류", "Yahoo Finance · 참고용", error, now, _market_state(symbol, now), False) for key, (label, symbol) in _SYMBOLS.items()}
            _CACHE = (time.time(), metrics, error)
            return metrics, error


def market_diagnostics() -> dict[str, Any]:
    with _CACHE_LOCK:
        return {"source": "Yahoo Finance · 참고용", "call_count": _CALL_COUNT, "last_attempt_at": _LAST_ATTEMPT_AT, "last_success_at": _LAST_SUCCESS_AT, "last_error": _LAST_ERROR, "next_refresh_at": _NEXT_REFRESH_AT, "cache_ttl_seconds": _CACHE_TTL_SECONDS, "stale_ttl_seconds": _STALE_TTL_SECONDS}


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
    verified = [item for item in valid if item.verified]
    latest = max((item.updated_at or 0 for item in valid), default=None)
    if len(verified) == len(metrics) and not error:
        status = "정상"
    elif valid:
        status = "주의"
    else:
        status = "오류"
    detail = f"값 {len(valid)}/{len(metrics)} · 검증 {len(verified)}/{len(metrics)}"
    return {"status": status, "detail": detail, "checked_at": latest, "error": error}


def _load_sector_strength_from_db(path: Path, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    if not path.exists():
        return [], "시장 DB 파일이 없습니다."
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "sector_strength" not in tables:
                return [], "섹터 강도 계산 테이블이 없습니다."
            rows = conn.execute("SELECT sector, change_rate, breadth, relative_strength FROM sector_strength ORDER BY relative_strength DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) | {"source": "SQLite"} for row in rows], None
    except Exception as exc:
        return [], str(exc)


def _latest_business_date() -> str:
    seoul_now = datetime.now(ZoneInfo("Asia/Seoul"))
    for offset in range(0, 10):
        candidate = seoul_now.date() - pd.Timedelta(days=offset)
        if candidate.weekday() < 5:
            return candidate.strftime("%Y%m%d")
    return seoul_now.strftime("%Y%m%d")


def _calculate_live_sector_strength(limit: int) -> tuple[list[dict[str, Any]], str | None]:
    global _SECTOR_CACHE
    now = time.time()
    if _SECTOR_CACHE and now - _SECTOR_CACHE[0] <= _SECTOR_CACHE_TTL_SECONDS:
        return _SECTOR_CACHE[1][:limit], _SECTOR_CACHE[2]
    if pykrx_stock is None:
        return [], "pykrx를 불러오지 못했습니다."
    business_date = _latest_business_date()
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for market in ("KOSPI", "KOSDAQ"):
        try:
            tickers = pykrx_stock.get_index_ticker_list(business_date, market=market)
            for ticker in tickers:
                try:
                    name = pykrx_stock.get_index_ticker_name(ticker)
                    ohlcv = pykrx_stock.get_index_ohlcv_by_date(business_date, business_date, ticker)
                    if ohlcv is None or ohlcv.empty:
                        continue
                    row = ohlcv.iloc[-1]
                    close = float(row.get("종가", 0) or 0)
                    change_rate = float(row.get("등락률", 0) or 0)
                    volume = float(row.get("거래량", 0) or 0)
                    turnover = float(row.get("거래대금", 0) or 0)
                    if close <= 0:
                        continue
                    strength = max(0.0, min(100.0, 50.0 + change_rate * 8.0))
                    rows.append({
                        "sector": f"{market} · {name}",
                        "change_rate": round(change_rate, 2),
                        "breadth": None,
                        "relative_strength": round(strength, 1),
                        "turnover": int(turnover),
                        "volume": int(volume),
                        "source": "pykrx 업종지수",
                        "as_of": business_date,
                    })
                except Exception:
                    continue
        except Exception as exc:
            errors.append(f"{market}: {exc}")
    rows.sort(key=lambda item: (float(item.get("relative_strength") or 0), float(item.get("turnover") or 0)), reverse=True)
    warning = " | ".join(errors) if errors else None
    _SECTOR_CACHE = (now, rows, warning)
    return rows[:limit], warning


def load_sector_strength(db_path: str | Path, *, limit: int = 10, refresh: bool = False) -> tuple[list[dict[str, Any]], str | None]:
    global _SECTOR_CACHE
    if refresh:
        _SECTOR_CACHE = None
    db_rows, db_error = _load_sector_strength_from_db(Path(db_path), limit)
    if db_rows:
        return db_rows, db_error
    live_rows, live_error = _calculate_live_sector_strength(limit)
    if live_rows:
        warning = db_error if db_error else live_error
        return live_rows, warning
    errors = [message for message in (db_error, live_error) if message]
    return [], " · ".join(errors) if errors else "섹터 강도 데이터를 계산하지 못했습니다."
