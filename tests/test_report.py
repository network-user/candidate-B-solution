import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from report import build

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ON = date(2026, 11, 10)


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.contracts, self.works, _payments, self.totals = build(DATA, ON)
        self.by_id = {w.work_id: w for w in self.works}

    def test_d1_allocation(self):
        self.assertEqual(self.by_id["W-11"].paid, Decimal("100000.00"))
        self.assertEqual(self.by_id["W-11"].left, Decimal("0.00"))
        self.assertEqual(self.by_id["W-12"].paid, Decimal("100000.00"))
        self.assertEqual(self.by_id["W-14"].paid_direct, Decimal("15000.00"))
        self.assertEqual(self.by_id["W-14"].paid_advance, Decimal("85000.00"))
        self.assertEqual(self.by_id["W-14"].left, Decimal("0.00"))
        self.assertEqual(self.by_id["W-13"].status, "cancelled")
        self.assertEqual(self.by_id["W-13"].due, Decimal("0.00"))
        self.assertEqual(self.by_id["W-15"].paid, Decimal("0.00"))
        self.assertEqual(self.by_id["W-15"].left, Decimal("100000.00"))
        self.assertEqual(self.by_id["W-16"].left, Decimal("100000.00"))
        self.assertEqual(self.totals["D-1"]["paid"], Decimal("315000.00"))
        self.assertEqual(self.totals["D-1"]["refunded"], Decimal("50000.00"))
        self.assertEqual(self.totals["D-1"]["queued"], Decimal("150000.00"))
        self.assertEqual(self.totals["D-1"]["unallocated"], Decimal("15000.00"))

    def test_d2_future_completion_and_payment_excluded(self):
        self.assertEqual(self.by_id["W-23"].status, "planned")
        self.assertEqual(self.by_id["W-23"].paid, Decimal("0.00"))
        self.assertEqual(self.by_id["W-23"].left, Decimal("40000.00"))
        self.assertEqual(self.by_id["W-21"].paid, Decimal("20000.00"))
        self.assertEqual(self.by_id["W-22"].paid, Decimal("30000.00"))
        self.assertEqual(self.totals["D-2"]["paid"], Decimal("75000.00"))
        self.assertEqual(self.totals["D-2"]["unallocated"], Decimal("25000.00"))

    def test_kopecks_stay_exact(self):
        due = sum((w.due for w in self.works if w.contract_id == "D-1"), Decimal("0.00"))
        left_cash = due - self.totals["D-1"]["paid"]
        self.assertEqual(left_cash, Decimal("185000.00"))
        self.assertEqual(left_cash, sum((w.left for w in self.works if w.contract_id == "D-1"), Decimal("0")) - self.totals["D-1"]["unallocated"])


if __name__ == "__main__":
    unittest.main()
