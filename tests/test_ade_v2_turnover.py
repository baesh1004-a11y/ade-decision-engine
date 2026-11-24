import unittest
from ade_v2.turnover import report_turnover


class TestTurnover(unittest.TestCase):
    def test_buy_sell_counted_once(self):
        r = report_turnover(confirmed_buy=4_000_000, confirmed_sell=6_000_000,
                            reason="RISK_GATES")
        self.assertEqual(r.achieved, 10_000_000)
        self.assertAlmostEqual(r.achievement_pct, 66.6666666667)
        self.assertEqual(r.shortfall, 5_000_000)

    def test_percentage_overflow_rejected(self):
        with self.assertRaisesRegex(ValueError, "percentage overflow"):
            report_turnover(confirmed_buy=1e308, confirmed_sell=0, target=1e-300)

    def test_large_equal_amounts_stay_finite(self):
        r = report_turnover(confirmed_buy=1e308, confirmed_sell=0, target=1e308)
        self.assertEqual(r.achievement_pct, 100)

    def test_full_target(self):
        r = report_turnover(confirmed_buy=9_000_000, confirmed_sell=6_000_000)
        self.assertEqual(r.achievement_pct, 100)
        self.assertIsNone(r.shortfall_reason)

    def test_no_implicit_zero_for_missing_fills(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=None, confirmed_sell=0, reason="UNKNOWN")

    def test_rejects_boolean_and_string_amounts(self):
        for bad in (True, False, "100", [], None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    report_turnover(confirmed_buy=bad, confirmed_sell=0, reason="BLOCKED")

    def test_oversized_integer_rejected_cleanly(self):
        for field in ("confirmed_buy", "confirmed_sell", "target"):
            with self.subTest(field=field):
                kwargs = {"confirmed_buy": 0, "confirmed_sell": 0,
                          "target": 15_000_000, "reason": "BLOCKED"}
                kwargs[field] = 10 ** 1000
                with self.assertRaisesRegex(ValueError, "Invalid turnover amounts"):
                    report_turnover(**kwargs)

    def test_rejects_overflowed_sum(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=1e308, confirmed_sell=1e308, reason="BLOCKED")

    def test_rejects_blank_shortfall_reason(self):
        for reason in ("", "   ", 1):
            with self.assertRaises(ValueError):
                report_turnover(confirmed_buy=0, confirmed_sell=0, reason=reason)

    def test_shortfall_requires_reason(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=0, confirmed_sell=0)

    def test_nonfinite_and_negative_rejected(self):
        for amount in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                report_turnover(confirmed_buy=amount, confirmed_sell=0, reason="BLOCKED")


if __name__ == "__main__":
    unittest.main()
