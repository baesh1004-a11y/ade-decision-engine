from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class UniverseSymbol:
    market: str
    ticker: str
    name: str | None = None
    sector: str | None = None
    source: str = "manual"
    tags: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.market.upper()}:{self.ticker.upper()}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UniverseBuildResult:
    total_candidates: int
    included_count: int
    excluded_count: int
    final_count: int
    symbols: list[UniverseSymbol]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "included_count": self.included_count,
            "excluded_count": self.excluded_count,
            "final_count": self.final_count,
            "symbols": [symbol.to_dict() for symbol in self.symbols],
        }
