import unittest

from ade_v2.validation import Snapshot, compare_out_of_sample


class TestOutOfSampleComparison(unittest.TestCase):
    def test_after_cost_nav_and_drawdown(self):
        rows = [
            Snapshot("2026-10-23", 100, 100, 100),
            Snapshot("2026-10-26", 98, 101, 99),
            Snapshot("2026-10-27", 99, 102, 103),
            Snapshot("2026-10-28", 97, 100, 105),
        ]
        result = compare_out_of_sample(rows, train_end="2026-10-23")
        self.assertAlmostEqual(result.baseline.return_pct, -3)
        self.assertAlmostEqual(result.candidate.return_pct, 0)
        self.assertAlmostEqual(result.candidate.max_drawdown_pct, (100 / 102 - 1) * 100)
        self.assertAlmostEqual(result.candidate_excess_pp, -5)

    def test_reject_future_leakage_or_unordered_dates(self):
        rows = [Snapshot("2026-10-23", 100, 100, 100),
                Snapshot("2026-10-22", 100, 100, 100)]
        with self.assertRaises(ValueError):
            compare_out_of_sample(rows, train_end="2026-10-23")

    def test_reject_missing_and_zero_prices(self):
        rows = [Snapshot("2026-10-23", 100, 100, 100),
                Snapshot("2026-10-26", 100, float("nan"), 100)]
        with self.assertRaises(ValueError):
            compare_out_of_sample(rows, train_end="2026-10-23")

    def test_reject_single_snapshot(self):
        with self.assertRaises(ValueError):
            compare_out_of_sample([Snapshot("2026-10-23", 100, 100, 100)],
                                  train_end="2026-10-23")


if __name__ == "__main__":
    unittest.main()
