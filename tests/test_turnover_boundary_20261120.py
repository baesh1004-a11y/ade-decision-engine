"""Boundary regression tests for confirmed-fill turnover; no fabricated executions."""
import unittest

from ade_v2.turnover import report_turnover


class TurnoverBoundaryTests(unittest.TestCase):
    def test_exact_target(self):
        r = report_turnover(confirmed_buy=10_000_000, confirmed_sell=5_000_000)
        self.assertEqual((r.achievement_pct, r.shortfall, r.shortfall_reason), (100, 0, None))

    def test_verified_shortfall_reason(self):
        r = report_turnover(confirmed_buy=1, confirmed_sell=2, reason="settlement restriction")
        self.assertEqual(r.shortfall_reason, "settlement restriction")

    def test_missing_shortfall_reason_rejected(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=1, confirmed_sell=2)

    def test_huge_integer_rejected(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=10**1000, confirmed_sell=0)

    def test_float_sum_overflow_rejected(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=1e308, confirmed_sell=1e308)

    def test_boolean_rejected(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=True, confirmed_sell=0)
