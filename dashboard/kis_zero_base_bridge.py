from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from broker.base import BrokerOrder, OrderResult
from broker.kis import KISBrokerAdapter, kis_broker_from_env, kis_config_from_env
from broker.kis_account_sync import KISAccountSync


_REQUIRED_ENV = ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT")


def kis_configured() -> bool:
    return all(os.getenv(key, "").strip() for key in _REQUIRED_ENV)


def kis_paper_enabled() -> bool:
    if not kis_configured():
        return False
    try:
        return not kis_config_from_env().is_live
    except Exception:
        return False


def _broker() -> KISBrokerAdapter:
    return kis_broker_from_env()


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
            except Exception as exc:
                error = str(exc)
                account = sync.latest_account()
                positions = sync.latest_positions()
        elif not kis_configured():
            error = "KIS 환경변수가 설정되지 않았습니다."
        return account, positions, error
    finally:
        sync.close()


def load_kis_quote(ticker: str) -> tuple[dict[str, Any] | None, str | None]:
    if not kis_configured():
        return None, "KIS 환경변수가 설정되지 않았습니다."
    try:
        return _broker().get_quote(ticker), None
    except Exception as exc:
        return None, str(exc)


def load_orderable(ticker: str, price: float, order_type: str) -> tuple[dict[str, Any] | None, str | None]:
    if not kis_paper_enabled():
        return None, "KIS 모의투자 환경이 아닙니다."
    try:
        return _broker().get_orderable(ticker, price, order_type), None
    except Exception as exc:
        return None, str(exc)


def load_daily_orders(executed_only: bool = False) -> tuple[list[dict[str, Any]], str | None]:
    if not kis_configured():
        return [], "KIS 환경변수가 설정되지 않았습니다."
    try:
        return _broker().get_daily_orders(executed_only=executed_only), None
    except Exception as exc:
        return [], str(exc)


def load_pending_orders() -> tuple[list[dict[str, Any]], str | None]:
    if not kis_configured():
        return [], "KIS 환경변수가 설정되지 않았습니다."
    try:
        return _broker().get_pending_orders(), None
    except Exception as exc:
        return [], str(exc)


def revise_paper_order(order_id: str, quantity: int, price: float) -> dict[str, Any]:
    if not kis_paper_enabled():
        raise RuntimeError("KIS 모의투자 환경이 아니거나 설정이 완전하지 않습니다.")
    return _broker().revise_or_cancel_order(order_id, quantity, price=price, cancel=False)


def cancel_paper_order(order_id: str, quantity: int) -> dict[str, Any]:
    if not kis_paper_enabled():
        raise RuntimeError("KIS 모의투자 환경이 아니거나 설정이 완전하지 않습니다.")
    return _broker().revise_or_cancel_order(order_id, quantity, cancel=True)


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
    return _broker().place_order(order)
