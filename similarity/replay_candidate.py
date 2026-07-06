from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReplayCandidate:
    event_id: str
    weekly_similarity: float
    sto_similarity: float
    final_similarity: float
    weekly_pattern: str | None = None
    sto_structure: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
