from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
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
    primary_value = os.getenv(primary, "").strip()
    if primary_value:
        return primary_value
    for alias in aliases:
        alias_value = os.getenv(alias, "").strip()
        if alias_value:
            return alias_value
    return default


def kis_configured() -> bool:
    account = _resolve_env("KIS_ACCOUNT_NO", "KIS_ACCOUNT")
    return bool(os.getenv("KIS_APP_KEY", "").strip() and os.getenv("KIS_APP_SECRET", "").strip() and account)


def kis_configuration_status() -> dict[str, Any]:
    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    env = os.getenv("KIS_ENV", "paper").strip().lower() or "paper"
    account_no = os.getenv("KIS_ACCOUNT_NO", "").strip()
    account_alias = os.getenv("KIS_ACCOUNT", "").strip()
    product_primary = os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "").strip()
    product_alias = os.getenv("KIS_PRODUCT_CODE", "").strip()

    account = account_no or account_alias
    product = product_primary or product_alias or "01"
    warning = None
    if account_no and account_alias and account_no.replace("-", "") != account_alias.replace("-", ""):
        warning = "KIS_ACCOUNT_NO와 KIS_ACCOUNT 값이 다릅니다. KIS_ACCOUNT_NO를 우선 사용합니다."

    missing = []
    if not app_key:
        missing.append("KIS_APP_KEY")
    if not app_secret:
        missing.append("KIS_APP_SECRET")
    if not account:
        missing.append("KIS_ACCOUNT_NO 또는 KIS_ACCOUNT")

    account_source = "KIS_ACCOUNT_NO" if account_no else ("KIS_ACCOUNT" if account_alias else "미설정")
    product_source = "KIS_ACCOUNT_PRODUCT_CODE" if product_primary else ("KIS_PRODUCT_CODE" if product_alias else "기본값")
    configured = not missing
    paper = configured and env in {"paper", "virtual", "mock", "demo"}

    return {
        "configured": configured,
        "paper_enabled": paper,
        "environment": env,
        "account_source": account_source,
        "product_source": product_source,
        "product_code": product,
        "missing": missing,
        "warning": warning,
        "app_key_present": bool(app_key),
        "app_secret_present": bool(app_secret),
        "account_present": bool(account),
    }


def probe_kis_connection(db_path: str | Path) -> dict[str, Any]:
    status = kis_configuration_status()
    result: dict[str, Any] = {
        "configuration": status,
        "rest_ok": False,
        "account_ok": False,
        "position_count": 0,
        "captured_at": None,
        "error": None,
    }
    if not status["configured"]:
        result["error"] = "누락: " + ", ".join(status["missing"])
        return result
    try:
        snapshot, positions = KISAccountSync(db_path).sync(broker=_broker())
        account = snapshot.to_dict()
        _invalidate(_snapshot_cache_key(db_path))
        invalidate_order_caches()
        result.update(
            {
                "rest_ok": True,
                "account_ok": True,
                "position_count": len(positions),
                "captured_at": account.get("captured_at"),
                "cash": account.get("cash"),
                "evaluation_amount": account.get("evaluation_amount"),
            }
        )
    except Exception as exc:
        result["error"] = str(exc)
    return result


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


def _snapshot_age_seconds(account: dict[str, Any] | None) -> float | None:
    if not account:
        return None
    raw = account.get("captured_at")
    if not raw:
        return None
    try:
        captured = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        return max(0.0, time.time() - captured.timestamp())
    except Exception:
        return None


def read_kis_snapshot(
    db_path: str | Path,
    *,
    refresh_cache: bool = False,
    cache_seconds: float = 15.0,
    max_age_seconds: int = 60,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    del max_age_seconds
    if not kis_configured():
        status = kis_configuration_status()
        return None, [], "KIS 설정 확인 필요 · 누락: " + ", ".join(status.get("missing") or [])
    key = _snapshot_cache_key(db_path)
    if refresh_cache:
        _invalidate(key)
    try:
        account, positions = _cached(key, cache_seconds, lambda: KISAccountSync(db_path).latest_snapshot())
        if account is None:
            return None, [], "저장된 KIS 계좌 스냅샷이 없습니다. 새로고침이 필요합니다."
        age = _snapshot_age_seconds(account)
        warning = None
        if age is None:
            warning = "KIS 계좌 스냅샷 시각을 확인할 수 없습니다."
        elif age > 60:
            warning = f"최근 저장된 KIS 계좌 데이터입니다. 마지막 수신 후 {int(age)}초 경과"
        return account, positions, warning
    except Exception as exc:
        return None, [], str(exc)


def refresh_kis_snapshot(
    db_path: str | Path,
    *,
    max_age_seconds: int = 60,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    if not kis_configured():
        status = kis_configuration_status()
        return None, [], "KIS 설정 확인 필요 · 누락: " + ", ".join(status.get("missing") or [])
    try:
        snapshot, positions = KISAccountSync(db_path).sync(broker=_broker())
        account = snapshot.to_dict()
        _invalidate(_snapshot_cache_key(db_path))
        invalidate_order_caches()
        return account, positions, None
    except Exception as exc:
        account, positions, cached_error = read_kis_snapshot(
            db_path,
            refresh_cache=True,
            max_age_seconds=max_age_seconds,
        )
        if account is not None:
            warning = f"KIS 실시간 갱신 실패 · 최근 저장값 사용: {exc}"
            if cached_error:
                warning += f" · {cached_error}"
            return account, positions, warning
        return None, [], f"KIS 계좌 조회 실패: {exc}" + (f" · {cached_error}" if cached_error else "")


def load_kis_snapshot(
    db_path: str | Path,
    *,
    refresh: bool = False,
    max_age_seconds: int = 60,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    return (
        refresh_kis_snapshot(db_path, max_age_seconds=max_age_seconds)
        if refresh
        else read_kis_snapshot(db_path, max_age_seconds=max_age_seconds)
    )


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
