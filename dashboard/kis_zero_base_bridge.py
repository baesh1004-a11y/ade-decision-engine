from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from broker.kis_account_sync import KISAccountSync


_REQUIRED_ENV = ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT")


def kis_configured() -> bool:
    return all(os.getenv(key, "").strip() for key in _REQUIRED_ENV)


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
    """Return the latest KIS snapshot and refresh it when configured and stale.

    The function never blocks the UI on a failed broker request when a prior valid
    snapshot exists. The caller receives the last valid data plus an error message.
    """
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
            except Exception as exc:  # Last valid snapshot remains usable.
                error = str(exc)
                account = sync.latest_account()
                positions = sync.latest_positions()
        elif not kis_configured():
            error = "KIS 환경변수가 설정되지 않았습니다."

        return account, positions, error
    finally:
        sync.close()
