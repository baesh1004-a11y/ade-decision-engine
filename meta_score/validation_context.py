from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationContext:
    """External validation inputs produced outside MetaScoreEngine.

    Market and sector analysis are separate stages. MetaScoreEngine only
    consumes their final signals and does not execute JP Radar itself.
    """

    market_signal: str = "HOLD"
    sector_signal: str = "HOLD"


NEUTRAL_VALIDATION_CONTEXT = ValidationContext()
