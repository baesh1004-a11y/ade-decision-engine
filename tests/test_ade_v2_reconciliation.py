import unittest
from ade_v2.reconciliation import ConfirmedFill, FillReconciler


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.r = FillReconciler()
        self.fill = ConfirmedFill("F1", "O1", "005930", "BUY", 2, 100000)
        self.kw = dict(expected_order_id="O1", expected_ticker="005930", expected_side="BUY", ordered_quantity=3)

    def test_idempotent_replay(self):
        self.assertTrue(self.r.accept(self.fill, **self.kw))
        self.assertFalse(self.r.accept(self.fill, **self.kw))
        self.assertEqual(self.r.filled_qty["O1"], 2)

    def test_conflicting_duplicate_rejected(self):
        self.r.accept(self.fill, **self.kw)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.r.accept(ConfirmedFill("F1", "O1", "005930", "BUY", 1, 100000), **self.kw)

    def test_partial_fills_and_overfill(self):
        self.r.accept(self.fill, **self.kw)
        self.assertTrue(self.r.accept(ConfirmedFill("F2", "O1", "005930", "BUY", 1, 100100), **self.kw))
        with self.assertRaisesRegex(ValueError, "Overfill"):
            self.r.accept(ConfirmedFill("F3", "O1", "005930", "BUY", 1, 100200), **self.kw)
        self.assertEqual(self.r.filled_qty["O1"], 3)

    def test_identity_mismatch(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.r.accept(self.fill, **{**self.kw, "expected_side": "SELL"})
        self.assertFalse(self.r.seen)

    def test_invalid_price_and_quantity(self):
        for price in (float("nan"), float("inf"), -1):
            with self.assertRaisesRegex(ValueError, "price"):
                self.r.accept(ConfirmedFill("F1", "O1", "005930", "BUY", 2, price), **self.kw)
        with self.assertRaisesRegex(ValueError, "quantity"):
            self.r.accept(ConfirmedFill("F1", "O1", "005930", "BUY", 0, 100), **self.kw)
        self.assertFalse(self.r.seen)


if __name__ == "__main__":
    unittest.main()
