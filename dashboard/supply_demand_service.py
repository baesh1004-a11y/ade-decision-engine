from __future__ import annotations

import time
from datetime import datetime, timedelta
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

try:
    from pykrx import stock as pykrx_stock
except Exception:  # pragma: no cover
    pykrx_stock = None

_CACHE_LOCK = RLock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 10 * 60


def _normalize_ticker(ticker: str) -> str:
    digits = "".join(ch for ch in str(ticker or "") if ch.isdigit())
    return digits[-6:].zfill(6) if digits else str(ticker or "").strip()


def _business_dates(days: int = 20) -> list[str]:
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    dates: list[str] = []
    for offset in range(days):
        value = today - timedelta(days=offset)
        if value.weekday() < 5:
            dates.append(value.strftime("%Y%m%d"))
    return dates


def _sum_column(frame: Any, names: tuple[str, ...]) -> float | None:
    if frame is None or getattr(frame, "empty", True):
        return None
    for name in names:
        if name in frame.columns:
            series = frame[name].dropna()
            if not series.empty:
                return float(series.sum())
    return None


def _load_investor_flow(ticker: str) -> dict[str, Any]:
    errors: list[str] = []
    for end in _business_dates():
        start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=14)).strftime("%Y%m%d")
        try:
            frame = pykrx_stock.get_market_trading_value_by_date(start, end, ticker)
            if frame is None or frame.empty:
                continue
            foreign = _sum_column(frame, ("외국인합계", "외국인"))
            institution = _sum_column(frame, ("기관합계", "기관"))
            if foreign is None and institution is None:
                errors.append(f"{end}: 투자자별 컬럼 없음")
                continue
            return {
                "status": "정상",
                "detail": f"최근 2주 순매수 · 외국인 {foreign or 0:,.0f}원 · 기관 {institution or 0:,.0f}원",
                "as_of": end,
            }
        except Exception as exc:
            errors.append(f"{end}: {type(exc).__name__}: {exc}")
    return {
        "status": "오류",
        "detail": errors[-1] if errors else "pykrx 투자자별 거래대금 조회 결과 없음",
        "as_of": None,
    }


def _load_shorting(ticker: str) -> dict[str, Any]:
    errors: list[str] = []
    for end in _business_dates():
        start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=14)).strftime("%Y%m%d")
        try:
            frame = pykrx_stock.get_shorting_value_by_date(start, end, ticker)
            if frame is None or frame.empty:
                continue
            short_value = _sum_column(frame, ("공매도", "공매도거래대금", "거래대금"))
            if short_value is None:
                errors.append(f"{end}: 공매도 컬럼 없음")
                continue
            return {
                "status": "정상",
                "detail": f"최근 2주 공매도 거래대금 {short_value:,.0f}원 · 프로그램매매는 별도 공급원 필요",
                "as_of": end,
            }
        except Exception as exc:
            errors.append(f"{end}: {type(exc).__name__}: {exc}")
    return {
        "status": "오류",
        "detail": errors[-1] if errors else "pykrx 공매도 조회 결과 없음",
        "as_of": None,
    }


def load_supply_demand_health(ticker: str, *, market: str = "kr", refresh: bool = False) -> dict[str, dict[str, Any]]:
    if market != "kr":
        return {
            "investor": {"status": "대기", "detail": "국내 종목만 수급 데이터를 확인합니다.", "as_of": None},
            "program_short": {"status": "대기", "detail": "국내 종목만 수급 데이터를 확인합니다.", "as_of": None},
        }
    if pykrx_stock is None:
        unavailable = {"status": "오류", "detail": "pykrx 모듈을 불러오지 못했습니다.", "as_of": None}
        return {"investor": unavailable, "program_short": unavailable}

    normalized = _normalize_ticker(ticker)
    key = f"{market}:{normalized}"
    now = time.time()
    with _CACHE_LOCK:
        if not refresh and key in _CACHE and now - _CACHE[key][0] <= _CACHE_TTL_SECONDS:
            return _CACHE[key][1]

    result = {
        "investor": _load_investor_flow(normalized),
        "program_short": _load_shorting(normalized),
    }
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), result)
    return result
