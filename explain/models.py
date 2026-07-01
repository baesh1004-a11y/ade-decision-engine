from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvidenceItem:
    category: str
    label: str
    value: str
    impact: str
    weight: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExplanationReport:
    engine_version: str
    ticker: str
    decision: str
    confidence: float
    summary: str
    evidence: list[dict[str, Any]]
    warnings: list[str]
    narrative: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
