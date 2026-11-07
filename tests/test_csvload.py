# tests/test_csvload.py — strict parsing: Decimal only, required columns, clear errors, size cap.
import unittest
from decimal import Decimal

from core.csvload import MAX_BYTES, CsvError, parse_bank, parse_ledger
from core.models import money

BANK = "# SYNTHETIC\ntxn_id,date,amount,direction,counterparty,reference,memo\nB1,2026-10-03,120.50,DR,Acme,ACM-1,\n"
LEDGER = ("inv_id,vendor,vendor_known,inv_date,due_date,amount,reference,gl_account\n"
          "INV-1,Acme,Y,2026-10-01,2026-10-31,120.50,ACM-1,6100\n")


class CsvLoadTest(unittest.TestCase):
    def test_bank_ok_decimal(self):
        b = parse_bank(BANK)[0]
        self.assertEqual(b.amount, Decimal("120.50"))
        self.assertIsInstance(b.amount, Decimal)
        self.assertEqual(b.memo, "")

    def test_ledger_ok(self):
        l = parse_ledger(LEDGER)[0]
        self.assertTrue(l.vendor_known)
        self.assertEqual(l.amount, Decimal("120.50"))

    def test_missing_column(self):
        with self.assertRaisesRegex(CsvError, "missing columns"):
            parse_bank("txn_id,date\nB1,2026-10-03\n")

    def test_bad_amount(self):
        with self.assertRaisesRegex(CsvError, "row 2"):
            parse_bank(BANK.replace("120.50", "12.345"))

    def test_bad_date(self):
        with self.assertRaisesRegex(CsvError, "bad date"):
            parse_bank(BANK.replace("2026-10-03", "03/10/2026"))

    def test_empty_required(self):
        with self.assertRaisesRegex(CsvError, "empty required"):
            parse_bank(BANK.replace("Acme", ""))

    def test_duplicate_id(self):
        with self.assertRaisesRegex(CsvError, "duplicate id"):
            parse_bank(BANK + "B1,2026-10-04,1.00,DR,Acme,ACM-2,\n")

    def test_size_cap(self):
        with self.assertRaisesRegex(CsvError, "exceeds"):
            parse_bank(BANK + "x" * MAX_BYTES)

    def test_money_rejects_float(self):
        with self.assertRaises(TypeError):
            money(1.1)
        with self.assertRaises(ValueError):
            money("abc")


if __name__ == "__main__":
    unittest.main()
