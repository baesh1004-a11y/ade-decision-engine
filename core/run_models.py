"""Portable contracts for recorded ADE runs; no market or broker side effects."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class RunStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


TERMINAL_RUNS = frozenset({"SUCCEEDED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED"})
TERMINAL_STAGES = frozenset({"SUCCEEDED", "FAILED", "SKIPPED"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Unsupported run artifact value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_json_default,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RunRequest:
    kind: str
    market: str
    parameters: dict[str, Any] = field(default_factory=dict)
    ticker: str | None = None
    input_hash: str | None = None
    idempotency_key: str | None = None
    run_id: str = field(default_factory=lambda: uuid4().hex)

    def fingerprint(self) -> str:
        payload = asdict(self)
        payload.pop("run_id")
        payload.pop("idempotency_key")
        return content_hash(payload)


@dataclass(frozen=True)
class StageResult:
    name: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    run_id: str
    kind: str
    market: str
    status: str
    created_at: str
    finished_at: str | None
    stages: tuple[StageResult, ...]
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
