"""No missing fill amounts may be silently interpreted as zero."""
import unittest
from ade_v2.turnover import report_turnover


class TestMissingEvidence(unittest.TestCase):
    def test_missing_buy_or_sell_rejected_even_with_shortfall_reason(self):
        for field in ("confirmed_buy", "confirmed_sell"):
            with self.subTest(field=field):
                amounts = dict(confirmed_buy=0, confirmed_sell=0, reason="UNRECONCILED")
                amounts[field] = None
                with self.assertRaises(ValueError):
                    report_turnover(**amounts)

    def test_unverified_nan_and_infinity_never_count_as_turnover(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            for field in ("confirmed_buy", "confirmed_sell"):
                with self.subTest(field=field, value=value):
                    amounts = dict(confirmed_buy=0, confirmed_sell=0, reason="UNRECONCILED")
                    amounts[field] = value
                    with self.assertRaises(ValueError):
                        report_turnover(**amounts)

    def test_zero_confirmed_fills_requires_explicit_verified_reason(self):
        with self.assertRaisesRegex(ValueError, "reason"):
            report_turnover(confirmed_buy=0, confirmed_sell=0)
        result = report_turnover(confirmed_buy=0, confirmed_sell=0, reason="NO_CONFIRMED_FILLS")
        self.assertEqual(result.achieved, 0)
        self.assertEqual(result.achievement_pct, 0)
        self.assertEqual(result.shortfall, 15_000_000)
        self.assertEqual(result.shortfall_reason, "NO_CONFIRMED_FILLS")


if __name__ == "__main__":
    unittest.main()
