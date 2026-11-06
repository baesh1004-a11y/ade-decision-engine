"""Strict out-of-sample NAV comparison, without fitting or inventing prices.

Inputs must be independently recorded after-cost NAV series for both strategies,
on the same dates. This module evaluates evidence; it does not train models.
"""
from dataclasses import dataclass
from datetime import date
from math import isfinite


@dataclass(frozen=True)
class Snapshot:
    day: str
    baseline_nav: float
    candidate_nav: float
    benchmark_close: float


@dataclass(frozen=True)
class Metrics:
    return_pct: float
    max_drawdown_pct: float


@dataclass(frozen=True)
class Comparison:
    baseline: Metrics
    candidate: Metrics
    benchmark: Metrics
    candidate_excess_pp: float
    baseline_excess_pp: float


def _metrics(values: list[float]) -> Metrics:
    high = values[0]
    mdd = 0.0
    for value in values:
        high = max(high, value)
        mdd = min(mdd, (value / high - 1) * 100)
    return Metrics((values[-1] / values[0] - 1) * 100, mdd)


def compare_out_of_sample(rows: list[Snapshot], *, train_end: str) -> Comparison:
    """Require a pre-test anchor and >=1 strictly later test observation.

    The first snapshot is the opening anchor at the train/test boundary.
    All subsequent snapshots must be after train_end, with no repeated dates.
    A training period and model fitting are NOT inferred from these snapshots.
    """
    cutoff = date.fromisoformat(train_end)
    if len(rows) < 2:
        raise ValueError("Need an anchor and at least one out-of-sample observation")
    days = [date.fromisoformat(row.day) for row in rows]
    if days[0] != cutoff or any(d <= cutoff for d in days[1:]):
        raise ValueError("Anchor must match train_end; test dates must be later")
    if any(a >= b for a, b in zip(days, days[1:])):
        raise ValueError("Dates must be strictly increasing")
    for row in rows:
        if not all(isfinite(x) and x > 0 for x in
                   (row.baseline_nav, row.candidate_nav, row.benchmark_close)):
            raise ValueError("Missing, nonfinite or nonpositive values are forbidden")
    baseline = _metrics([row.baseline_nav for row in rows])
    candidate = _metrics([row.candidate_nav for row in rows])
    benchmark = _metrics([row.benchmark_close for row in rows])
    return Comparison(baseline, candidate, benchmark,
                      candidate.return_pct - benchmark.return_pct,
                      baseline.return_pct - benchmark.return_pct)
