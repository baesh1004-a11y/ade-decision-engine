import unittest
from ade_v2.turnover import report_turnover


class TestTurnoverPolicyBoundary(unittest.TestCase):
    def test_partial_sell_and_buy_are_counted_once(self):
        result = report_turnover(confirmed_buy=2_500_000, confirmed_sell=4_000_000, reason="SETTLEMENT_BLOCK")
        self.assertEqual(result.achieved, 6_500_000)
        self.assertEqual(result.shortfall, 8_500_000)
        self.assertAlmostEqual(result.achievement_pct, 43.3333333333)
        self.assertEqual(result.shortfall_reason, "SETTLEMENT_BLOCK")

    def test_missing_sell_evidence_cannot_be_coerced_to_zero(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=1_000_000, confirmed_sell=None, reason="NO_FILL_EVIDENCE")

    def test_achieved_target_does_not_preserve_stale_shortfall_reason(self):
        result = report_turnover(confirmed_buy=10_000_000, confirmed_sell=5_000_000, reason="STALE_REASON")
        self.assertEqual(result.shortfall, 0)
        self.assertIsNone(result.shortfall_reason)


if __name__ == "__main__":
    unittest.main()
