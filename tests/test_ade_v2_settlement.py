import unittest
from datetime import date
from ade_v2.settlement import PendingCredit, SettlementBook, due_date


class SettlementTests(unittest.TestCase):
    def test_holiday_skipped(self):
        sessions = [date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 11)]
        self.assertEqual(due_date(sessions[0], sessions), sessions[2])

    def test_missing_calendar_fails_closed(self):
        with self.assertRaises(ValueError):
            due_date(date(2026, 11, 6), [date(2026, 11, 6)])

    def test_confirmation_required(self):
        book = SettlementBook()
        book.register(PendingCredit("F1", 100000.0, date(2026, 11, 10)))
        for day, confirmed in [(date(2026, 11, 9), True), (date(2026, 11, 10), False)]:
            with self.assertRaises(ValueError):
                book.confirm("F1", as_of=day, broker_confirmed=confirmed)
        self.assertEqual(book.confirm("F1", as_of=date(2026, 11, 10), broker_confirmed=True), 100000.0)

    def test_duplicate_rejected(self):
        book = SettlementBook()
        credit = PendingCredit("F1", 1.0, date(2026, 11, 10))
        book.register(credit)
        with self.assertRaises(ValueError):
            book.register(credit)

    def test_no_double_settlement(self):
        book = SettlementBook()
        book.register(PendingCredit("F1", 1.0, date(2026, 11, 10)))
        book.confirm("F1", as_of=date(2026, 11, 10), broker_confirmed=True)
        with self.assertRaises(ValueError):
            book.confirm("F1", as_of=date(2026, 11, 11), broker_confirmed=True)

    def test_invalid_amount(self):
        for amount in [float("nan"), float("inf"), -1.0, 0.0]:
            with self.assertRaises(ValueError):
                SettlementBook().register(PendingCredit("F1", amount, date(2026, 11, 10)))


if __name__ == "__main__":
    unittest.main()
