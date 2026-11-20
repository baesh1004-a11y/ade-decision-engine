"""Regression cases: confirmed-fill-only turnover and policy shortfall semantics."""
import unittest
from ade_v2.turnover import report_turnover

class TurnoverEvidenceRegression(unittest.TestCase):
    def test_exact_target_requires_no_shortfall_reason(self):
        r = report_turnover(confirmed_buy=7_500_000, confirmed_sell=7_500_000)
        self.assertEqual(r.achievement_pct, 100)
        self.assertEqual(r.shortfall, 0)
        self.assertIsNone(r.shortfall_reason)

    def test_verified_shortfall_retains_reason(self):
        r = report_turnover(confirmed_buy=1_000_000, confirmed_sell=0, reason='settlement cash unavailable')
        self.assertEqual(r.achieved, 1_000_000)
        self.assertEqual(r.shortfall, 14_000_000)
        self.assertEqual(r.shortfall_reason, 'settlement cash unavailable')

    def test_missing_evidence_must_not_be_zero(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=None, confirmed_sell=0, reason='no fill ledger')

    def test_unverified_shortfall_reason_is_rejected(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=0, confirmed_sell=0)

    def test_boolean_fill_is_rejected(self):
        with self.assertRaises(ValueError):
            report_turnover(confirmed_buy=True, confirmed_sell=0, reason='blocked')

if __name__ == '__main__':
    unittest.main()
