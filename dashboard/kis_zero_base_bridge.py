from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from threading import RLock
from typing import Any, Callable, TypeVar

from broker.base import BrokerOrder, OrderResult
from broker.kis import KISBrokerAdapter, kis_broker_from_env, kis_config_from_env
from broker.kis_account_sync import KISAccountSync


_T = TypeVar("_T")
_CACHE_LOCK = RLock()
_CACHE: dict[str, tuple[float, Any]] = {}
_BROKER_LOCK = RLock()
_BROKER: KISBrokerAdapter | None = None
_BROKER_FINGERPRINT: tuple[str, str, str, str] | None = None


def _resolve_env(primary: str, *aliases: str, default: str = "") -> str:
    values = [(name, os.getenv(name, "").strip()) for name in (primary, *aliases)]
    configured = [(name, value) for name, value in values if value]
    distinct = {value for _name, value in configured}
    if len(distinct) > 1:
        names = ", ".join(name for name, _value in configured)
        raise RuntimeError(f"충돌하는 KIS 환경변수 값: {names}")
    return configured[0][1] if configured else default


def kis_configured() -> bool:
    try:
        account = _resolve_env("KIS_ACCOUNT_NO", "KIS_ACCOUNT")
        _resolve_env("KIS_ACCOUNT_PRODUCT_CODE", "KIS_PRODUCT_CODE", default="01")
    except RuntimeError:
        return False
    return bool(os.getenv("KIS_APP_KEY", "").strip() and os.getenv("KIS_APP_SECRET", "").strip() and account)


def kis_configuration_status() -> dict[str, str]:
    account = _resolve_env("KIS_ACCOUNT_NO", "KIS_ACCOUNT")
    product = _resolve_env("KIS_ACCOUNT_PRODUCT_CODE", "KIS_PRODUCT_CODE", default="01")
    account_source = "KIS_ACCOUNT_NO" if os.getenv("KIS_ACCOUNT_NO", "").strip() else ("KIS_ACCOUNT" if account else "미설정")
    product_source = "KIS_ACCOUNT_PRODUCT_CODE" if os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "").strip() else ("KIS_PRODUCT_CODE" if os.getenv("KIS_PRODUCT_CODE", "").strip() else "기본값")
    return {
        "account_source": account_source,
        "product_source": product_source,
        "product_code": product,
    }


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
    account = _resolve_env("KIS_ACCOUNT_NO", "KIS_ACCOUNT")
    product = _resolve_env("KIS_ACCOUNT_PRODUCT_CODE", "KIS_PRODUCT_CODE", default="01")
    environment = os.getenv("KIS_ENV", "paper").strip().lower()
    secret_hash = hashlib.sha256(f"{app_key}:{app_secret}".encode("utf-8")).hexdigest()
    return environment, account, secret_hash, product


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


def invalidate_order_caches() -> None:
    _invalidate("orders:")
    _invalidate("orderable:")


def refresh_order_views() -> dict[str, Any]:
    invalidate_order_caches()
    pending, pending_error = load_pending_orders(refresh=True)
    daily, daily_error = load_daily_orders(executed_only=True, refresh=True)
    return {
        "pending_count": len(pending),
        "daily_count": len(daily),
        "pending_error": pending_error,
        "daily_error": daily_error,
    }


def _snapshot_cache_key(db_path: str | Path) -> str:
    return f"snapshot:{Path(db_path).resolve()}"


def read_kis_snapshot(
    db_path: str | Path,
    *,
    refresh_cache: bool = False,
    cache_seconds: float = 15.0,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    key = _snapshot_cache_key(db_path)
    if refresh_cache:
        _invalidate(key)
    try:
        account, positions = _cached(key, cache_seconds, lambda: KISAccountSync(db_path).latest_snapshot())
        error = None if kis_configured() else "KIS 환경변수가 설정되지 않았습니다."
        return account, positions, error
    except Exception as exc:
        return None, [], str(exc)


def refresh_kis_snapshot(db_path: str | Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    if not kis_configured():
        return read_kis_snapshot(db_path, refresh_cache=True)
    try:
        snapshot, positions = KISAccountSync(db_path).sync(broker=_broker())
        account = snapshot.to_dict()
        _invalidate(_snapshot_cache_key(db_path))
        invalidate_order_caches()
        return account, positions, None
    except Exception as exc:
        account, positions, _ = read_kis_snapshot(db_path, refresh_cache=True)
        return account, positions, str(exc)


def load_kis_snapshot(
    db_path: str | Path,
    *,
    refresh: bool = False,
    max_age_seconds: int = 60,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    del max_age_seconds
    return refresh_kis_snapshot(db_path) if refresh else read_kis_snapshot(db_path)


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
    result = _broker().revise_or_cancel_order(order_id, quantity, price=price, cancel=False, organization_no=organization_no)
    invalidate_order_caches()
    return result


def cancel_paper_order(
    order_id: str,
    quantity: int,
    *,
    organization_no: str = "",
) -> dict[str, Any]:
    if not kis_paper_enabled():
        raise RuntimeError("KIS 모의투자 환경이 아니거나 설정이 완전하지 않습니다.")
    result = _broker().revise_or_cancel_order(order_id, quantity, cancel=True, organization_no=organization_no)
    invalidate_order_caches()
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
    invalidate_order_caches()
    return result
