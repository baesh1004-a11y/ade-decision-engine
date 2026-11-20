"""Safety regressions: turnover is not a fill generator or a risk override."""
import pytest
from ade_v2.turnover import report_turnover


def test_verified_shortfall_requires_reason():
    with pytest.raises(ValueError, match="reason"):
        report_turnover(confirmed_buy=1_000_000, confirmed_sell=0)


def test_verified_shortfall_is_auditable():
    result = report_turnover(confirmed_buy=1_000_000, confirmed_sell=2_000_000, reason="cash floor blocked further buys")
    assert result.achieved == 3_000_000
    assert result.shortfall == 12_000_000
    assert result.achievement_pct == 20


def test_no_fabricated_turnover_from_missing_fills():
    with pytest.raises(ValueError):
        report_turnover(confirmed_buy=None, confirmed_sell=0, reason="unreconciled")


def test_over_target_has_no_shortfall():
    result = report_turnover(confirmed_buy=10_000_000, confirmed_sell=6_000_000)
    assert result.shortfall == 0
    assert result.shortfall_reason is None
    assert result.achievement_pct > 100
