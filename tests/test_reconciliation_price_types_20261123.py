import unittest
from ade_v2.reconciliation import ConfirmedFill, FillReconciler


class FillPriceTypeRegressionTests(unittest.TestCase):
    def test_nonnumeric_prices_rejected_without_ledger_mutation(self):
        for price in ("100", True, None, [], {}):
            with self.subTest(price=repr(price)):
                reconciler = FillReconciler()
                fill = ConfirmedFill("F1", "O1", "005930", "BUY", 1, price)
                with self.assertRaisesRegex(ValueError, "Invalid fill price"):
                    reconciler.accept(fill, expected_order_id="O1",
                                      expected_ticker="005930",
                                      expected_side="BUY", ordered_quantity=1)
                self.assertFalse(reconciler.seen)
                self.assertFalse(reconciler.filled_qty)

    def test_numeric_price_still_accepted(self):
        reconciler = FillReconciler()
        fill = ConfirmedFill("F1", "O1", "005930", "BUY", 1, 100)
        self.assertTrue(reconciler.accept(
            fill, expected_order_id="O1", expected_ticker="005930",
            expected_side="BUY", ordered_quantity=1))


if __name__ == "__main__":
    unittest.main()
