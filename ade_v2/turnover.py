"""Auditable turnover accounting. Only confirmed fills count toward the target.

This module does not infer executions from order submissions or price signals.
"""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class TurnoverReport:
    target: float
    confirmed_buy: float
    confirmed_sell: float
    achieved: float
    achievement_pct: float
    shortfall: float
    shortfall_reason: str | None


def report_turnover(*, confirmed_buy: float, confirmed_sell: float,
                    target: float = 15_000_000,
                    reason: str | None = None) -> TurnoverReport:
    """Compute fill-only turnover; missing fills must not be represented as zero.

    Caller must independently reconcile all fills before passing amounts.
    """
    amounts = (confirmed_buy, confirmed_sell, target)
    if any(type(v) not in (int, float) for v in amounts):
        raise ValueError("Turnover amounts must be numeric, not booleans or strings")
    if not all(isfinite(v) for v in amounts) or any(v < 0 for v in amounts) or target == 0:
        raise ValueError("Invalid turnover amounts")
    achieved = confirmed_buy + confirmed_sell
    if not isfinite(achieved):
        raise ValueError("Turnover sum overflow")
    shortfall = max(0.0, target - achieved)
    if shortfall > 0 and (not isinstance(reason, str) or not reason.strip()):
        raise ValueError("A verified shortfall requires an explicit reason")
    achievement_pct = 100 * (achieved / target)
    if not isfinite(achievement_pct):
        raise ValueError("Turnover percentage overflow")
    return TurnoverReport(target, confirmed_buy, confirmed_sell, achieved,
                          achievement_pct, shortfall,
                          reason if shortfall else None)
