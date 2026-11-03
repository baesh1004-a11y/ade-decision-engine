import unittest
from ade_v2.turnover import report_turnover


class TestTurnover(unittest.TestCase):
    def test_buy_sell_counted_once(self):
        r = report_turnover(confirmed_buy=4_000_000, confirmed_sell=6_000_000,
                            reason="RISK_GATES")
        self.assertEqual(r.achieved, 10_000_000)
        self.assertAlmostEqual(r.achievement_pct, 66.6666666667)
        self.assertEqual(r.shortfall, 5_000_000)

    def test_full_target(self):
        r = report_turnover(confirmed_buy=9_000_000, confirmed_sell=6_000_000)
        self.assertEqual(r.achievement_pct, 100)
        self.assertIsNone(r.shortfall_reason)

    def test_no_implicit_zero_for_missing_fills(self):
        with self.assertRaises(TypeError):
            report_turnover(confirmed_buy=None, confirmed_sell=0, reason="UNKNOWN")

    def test_shortfall_requires_reason(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=0, confirmed_sell=0)

    def test_nonfinite_and_negative_rejected(self):
        for amount in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                report_turnover(confirmed_buy=amount, confirmed_sell=0, reason="BLOCKED")


if __name__ == "__main__":
    unittest.main()
