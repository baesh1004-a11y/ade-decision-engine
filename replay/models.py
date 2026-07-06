from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ADE_VERSION = "2.0"


@dataclass(frozen=True)
class ReplayEvent:
    event_id: str
    ade_version: str
    market: str
    ticker: str
    name: str | None
    event_date: str
    money_ratio_20d: float
    money_ratio_120d: float
    bullish_body: bool
    long_base: bool
    sto_state: str
    ma_state: str
    weekly_position: str
    money_flow: str
    year_center: float | None
    half_center: float | None
    quarter_center: float | None
    month_center: float | None
    event_end_date: str | None
    event_end_reason: str | None
    max_return: float | None
    max_drawdown: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayEventFlow:
    event_id: str
    day_index: int
    trade_date: str
    close: float
    volume: float
    return_pct: float
    drawdown_pct: float
    sto_state: str
    ma_state: str
    weekly_position: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
