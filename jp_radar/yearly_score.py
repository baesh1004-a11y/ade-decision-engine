from __future__ import annotations

from jp_radar.yearly_meaning import YearlyMeaning


YEARLY_STATE_SCORE = {
    "ABOVE_CLOSE": 10.0,
    "AT_CLOSE": 8.0,
    "BETWEEN": 5.0,
    "ABOVE_OPEN": 3.0,
    "AT_OPEN": 0.0,
    "BELOW_OPEN": -10.0,
}


def calculate_yearly_score(meaning: YearlyMeaning) -> float:
    """Return the yearly meaning score without changing existing radar signals."""
    return YEARLY_STATE_SCORE.get(meaning.state, 0.0)
