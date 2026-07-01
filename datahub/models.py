from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PriceBar:
    market: str
    ticker: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted_close: float | None = None
    source: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataHubSyncResult:
    market: str
    ticker: str
    source: str
    row_count: int
    start_date: str | None
    end_date: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
