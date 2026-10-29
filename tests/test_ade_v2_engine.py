import unittest
from ade_v2.engine import Ledger, Order, Policy, Signal, plan_orders, rank_signals


class TestADEv2(unittest.TestCase):
    def test_cash_and_weight_caps(self):
        p = Policy()
        ledger = Ledger(10_000_000)
        signals = [Signal(str(i), 100_000, .04, .01) for i in range(30)]
        orders, _ = plan_orders(ledger, {str(i): 100_000 for i in range(30)}, signals, p)
        self.assertTrue(all(o.quantity * o.reference_price <= 1_000_000 for o in orders))
        self.assertLessEqual(sum(o.quantity * o.reference_price * (1 + p.fee_rate) for o in orders), 9_000_000)

    def test_unsettled_proceeds_not_reusable(self):
        p = Policy()
        ledger = Ledger(1_000_000, {"OLD": 10}, {"OLD": 500_000})
        ledger.apply_confirmed_fill(Order("OLD", "SELL", 10, 100_000, "EXIT"), 100_000, p)
        self.assertEqual(ledger.settled_cash, 1_000_000)
        self.assertGreater(ledger.pending_settlement, 0)
        with self.assertRaises(ValueError):
            ledger.apply_confirmed_fill(Order("NEW", "BUY", 11, 100_000, "BUY"), 100_000, p)

    def test_rejected_fill_does_not_mutate(self):
        ledger = Ledger(100_000)
        with self.assertRaises(ValueError):
            ledger.apply_confirmed_fill(Order("X", "BUY", 2, 100_000, "BUY"), 100_000, Policy())
        self.assertEqual(ledger.settled_cash, 100_000)
        self.assertFalse(ledger.positions)

    def test_sell_realized_pnl(self):
        ledger = Ledger(100_000, {"X": 2}, {"X": 100_000})
        ledger.apply_confirmed_fill(Order("X", "SELL", 1, 60_000, "EXIT"), 60_000, Policy())
        self.assertGreater(ledger.realized_pnl, 0)
        self.assertEqual(ledger.positions["X"], 1)

    def test_net_edge_filter(self):
        orders, reasons = plan_orders(Ledger(10_000_000), {"X": 100_000},
                                      [Signal("X", 100_000, .001, .001)])
        self.assertFalse(orders)
        self.assertEqual(reasons["X"], "NONPOSITIVE_NET_EDGE")

    def test_ranking(self):
        a, b = Signal("A", 100, .1, .01), Signal("B", 100, .03, .01)
        self.assertEqual(rank_signals([b, a], Policy())[0].ticker, "A")


if __name__ == "__main__":
    unittest.main()
