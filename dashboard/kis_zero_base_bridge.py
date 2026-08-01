from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Callable, TypeVar

from broker.base import BrokerOrder, OrderResult
from broker.kis import KISBrokerAdapter, kis_broker_from_env, kis_config_from_env
from broker.kis_account_sync import KISAccountSync


_REQUIRED_ENV = ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT")
_T = TypeVar("_T")
_CACHE_LOCK = RLock()
_CACHE: dict[str, tuple[float, Any]] = {}
_BROKER_LOCK = RLock()
_BROKER: KISBrokerAdapter | None = None
_BROKER_FINGERPRINT: tuple[str, str, str, str] | None = None


def kis_configured() -> bool:
    return all(os.getenv(key, "").strip() for key in _REQUIRED_ENV)


def kis_paper_enabled() -> bool:
    if not kis_configured():
        return False
    try:
        return not kis_config_from_env().is_live
    except Exception:
        return False


def _broker_fingerprint() -> tuple[str, str, str, str]:
    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    account = os.getenv("KIS_ACCOUNT", "").strip() or os.getenv("KIS_ACCOUNT_NO", "").strip()
    environment = os.getenv("KIS_ENV", "paper").strip().lower()
    secret_hash = hashlib.sha256(f"{app_key}:{app_secret}".encode("utf-8")).hexdigest()
    return environment, account, secret_hash, os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01").strip()


def _broker() -> KISBrokerAdapter:
    global _BROKER, _BROKER_FINGERPRINT
    fingerprint = _broker_fingerprint()
    with _BROKER_LOCK:
        if _BROKER is None or _BROKER_FINGERPRINT != fingerprint:
            _BROKER = kis_broker_from_env()
            _BROKER_FINGERPRINT = fingerprint
            _invalidate()
        return _BROKER


def _cached(key: str, ttl_seconds: float, loader: Callable[[], _T]) -> _T:
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and now - cached[0] <= ttl_seconds:
            return cached[1]
    value = loader()
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)
    return value


def _invalidate(prefix: str | None = None) -> None:
    with _CACHE_LOCK:
        if prefix is None:
            _CACHE.clear()
            return
        for key in list(_CACHE):
            if key.startswith(prefix):
                _CACHE.pop(key, None)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def load_kis_snapshot(
    db_path: str | Path,
    *,
    refresh: bool = False,
    max_age_seconds: int = 60,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    sync = KISAccountSync(db_path)
    error: str | None = None
    try:
        account = sync.latest_account()
        positions = sync.latest_positions()
        captured_at = _parse_time(account.get("captured_at") if account else None)
        stale = captured_at is None or datetime.now() - captured_at > timedelta(seconds=max_age_seconds)
        if kis_configured() and (refresh or stale):
            try:
                snapshot, positions = sync.sync()
                account = snapshot.to_dict()
                _invalidate("orderable:")
                _invalidate("orders:")
            except Exception as exc:
                error = str(exc)
                account = sync.latest_account()
                positions = sync.latest_positions()
        elif not kis_configured():
            error = "KIS 환경변수가 설정되지 않았습니다."
        return account, positions, error
    finally:
        sync.close()


def load_kis_quote(ticker: str, *, refresh: bool = False) -> tuple[dict[str, Any] | None, str | None]:
    if not kis_configured():
        return None, "KIS 환경변수가 설정되지 않았습니다."
    key = f"quote:{str(ticker).zfill(6)}"
    if refresh:
        _invalidate(key)
    try:
        return _cached(key, 5.0, lambda: _broker().get_quote(ticker)), None
    except Exception as exc:
        return None, str(exc)


def load_orderable(
    ticker: str,
    price: float,
    order_type: str,
    *,
    refresh: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    if not kis_paper_enabled():
        return None, "KIS 모의투자 환경이 아닙니다."
    normalized_price = 0 if order_type.upper() == "MARKET" else int(price)
    key = f"orderable:{str(ticker).zfill(6)}:{order_type.upper()}:{normalized_price}"
    if refresh:
        _invalidate(key)
    try:
        return _cached(key, 3.0, lambda: _broker().get_orderable(ticker, price, order_type)), None
    except Exception as exc:
        return None, str(exc)


def load_daily_orders(
    executed_only: bool = False,
    *,
    refresh: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    if not kis_configured():
        return [], "KIS 환경변수가 설정되지 않았습니다."
    key = f"orders:daily:{int(executed_only)}"
    if refresh:
        _invalidate(key)
    try:
        return _cached(key, 5.0, lambda: _broker().get_daily_orders(executed_only=executed_only)), None
    except Exception as exc:
        return [], str(exc)


def load_pending_orders(*, refresh: bool = False) -> tuple[list[dict[str, Any]], str | None]:
    if not kis_configured():
        return [], "KIS 환경변수가 설정되지 않았습니다."
    key = "orders:pending"
    if refresh:
        _invalidate(key)
    try:
        return _cached(key, 3.0, lambda: _broker().get_pending_orders()), None
    except Exception as exc:
        return [], str(exc)


def revise_paper_order(
    order_id: str,
    quantity: int,
    price: float,
    *,
    organization_no: str = "",
) -> dict[str, Any]:
    if not kis_paper_enabled():
        raise RuntimeError("KIS 모의투자 환경이 아니거나 설정이 완전하지 않습니다.")
    result = _broker().revise_or_cancel_order(
        order_id,
        quantity,
        price=price,
        cancel=False,
        organization_no=organization_no,
    )
    _invalidate("orders:")
    _invalidate("orderable:")
    return result


def cancel_paper_order(
    order_id: str,
    quantity: int,
    *,
    organization_no: str = "",
) -> dict[str, Any]:
    if not kis_paper_enabled():
        raise RuntimeError("KIS 모의투자 환경이 아니거나 설정이 완전하지 않습니다.")
    result = _broker().revise_or_cancel_order(
        order_id,
        quantity,
        cancel=True,
        organization_no=organization_no,
    )
    _invalidate("orders:")
    _invalidate("orderable:")
    return result


def submit_paper_order(
    *,
    ticker: str,
    side: str,
    quantity: int,
    order_type: str,
    limit_price: float | None,
) -> OrderResult:
    if not kis_paper_enabled():
        raise RuntimeError("KIS 모의투자 환경이 아니거나 설정이 완전하지 않습니다.")
    normalized_side = side.upper()
    normalized_type = order_type.upper()
    order = BrokerOrder(
        market="kr",
        ticker=str(ticker).strip(),
        side=normalized_side,
        quantity=int(quantity),
        order_type=normalized_type,
        limit_price=float(limit_price) if normalized_type == "LIMIT" and limit_price is not None else None,
        dry_run=False,
    )
    result = _broker().place_order(order)
    _invalidate("orders:")
    _invalidate("orderable:")
    return result