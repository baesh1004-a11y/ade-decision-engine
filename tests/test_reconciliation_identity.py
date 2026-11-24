import unittest
from ade_v2.reconciliation import ConfirmedFill, FillReconciler

class IdentityTests(unittest.TestCase):
    def test_invalid_identity_does_not_mutate(self):
        for bad in (123, True, '   ', [], None):
            for field in ('fill_id', 'order_id', 'ticker'):
                with self.subTest(bad=bad, field=field):
                    values = dict(fill_id='f1', order_id='o1', ticker='005930', side='SELL', quantity=1, price=100)
                    values[field] = bad
                    r = FillReconciler()
                    with self.assertRaises(ValueError):
                        r.accept(ConfirmedFill(**values), expected_order_id=values['order_id'], expected_ticker=values['ticker'], expected_side='SELL', ordered_quantity=2)
                    self.assertEqual((r.seen, r.filled_qty, r.order_identity), ({}, {}, {}))

    def test_valid_partial_and_duplicate(self):
        r = FillReconciler()
        kwargs = dict(expected_order_id='o1', expected_ticker='005930', expected_side='SELL', ordered_quantity=2)
        f = ConfirmedFill('f1', 'o1', '005930', 'SELL', 1, 100)
        self.assertTrue(r.accept(f, **kwargs))
        self.assertFalse(r.accept(f, **kwargs))
        self.assertTrue(r.accept(ConfirmedFill('f2', 'o1', '005930', 'SELL', 1, 101), **kwargs))
        self.assertEqual(r.filled_qty, {'o1': 2})
