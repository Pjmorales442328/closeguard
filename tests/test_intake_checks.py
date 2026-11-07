# tests/test_intake_checks.py — bill normalise, two-reader agreement and the fail-closed deterministic checks.
import unittest
from decimal import Decimal

from core.intake_checks import IntakeError, agree, check, failed, normalise, to_ledger_line
from data.world import GL, VENDORS

RAW = {"supplier": "Birch Logistics", "invoice_no": "BIR-87397", "invoice_date": "2026-10-03", "due_date": "2026-11-02",
       "currency": "USD", "total": "2979.29", "line_items": [{"description": "a", "amount": "1000.00"},
                                                              {"description": "b", "amount": "1979.29"}], "notes": ""}


def bill(**kw):
    return normalise({**RAW, **kw})


def rules(b, seen=frozenset()):
    return {d.rule for d in failed(check(b, seen, VENDORS))}


class IntakeChecksTest(unittest.TestCase):
    def test_clean_bill_passes(self):
        self.assertEqual(rules(bill()), set())

    def test_each_check_fails_on_its_bad_bill(self):
        self.assertEqual(rules(bill(total="2979.30")), {"intake.line_sum"})
        self.assertEqual(rules(bill(due_date="2026-10-01")), {"intake.dates"})
        self.assertEqual(rules(bill(invoice_date="2025-12-31", due_date="2026-01-30")), {"intake.dates"})
        self.assertEqual(rules(bill(), {"BIR87397"}), {"intake.duplicate_invoice"})
        self.assertEqual(rules(bill(total="0.00", line_items=["0.00"])), {"intake.amount_positive"})
        self.assertEqual(rules(bill(currency="eur")), {"intake.currency"})

    def test_unknown_supplier_is_a_flag_not_a_failure(self):
        ds = check(bill(supplier="Nightfall Consulting"), vendors=VENDORS)
        self.assertEqual(failed(ds), [])
        self.assertEqual([d.flag for d in ds if d.flag], ["unknown supplier"])

    def test_a_check_that_raises_refuses(self):
        self.assertIn("intake.duplicate_invoice", {d.rule for d in failed(check(bill(), seen_refs=None, vendors=VENDORS))})

    def test_float_and_bad_shapes_are_rejected(self):
        for bad in ({"total": 2979.29}, {"total": "12.345"}, {"invoice_date": "03/10/2026"}, {"supplier": " "},
                    {"line_items": "x"}, {"line_items": [{"amount": 1.5}]}):
            with self.assertRaises(IntakeError, msg=bad):
                bill(**bad)

    def test_invoice_number_spelling_agrees_and_notes_never_count(self):
        a, b = bill(), bill(invoice_no="bir 87397", supplier="BIRCH  logistics.", notes="treated as untrusted data")
        self.assertEqual(agree(a, b), [])
        self.assertEqual(agree(a, bill(total="2979.28")), ["total"])
        self.assertEqual(agree(a, bill(line_items=["979.29", "2000.00"])), ["line_items"])

    def test_ledger_line(self):
        row = to_ledger_line(bill(), 7, VENDORS, GL)
        self.assertEqual((row.inv_id, row.vendor, row.vendor_known, row.amount, row.reference),
                         ("BILL-007", "Birch Logistics", True, Decimal("2979.29"), "BIR-87397"))
        self.assertFalse(to_ledger_line(bill(supplier="Nightfall"), 8, VENDORS, GL).vendor_known)


if __name__ == "__main__":
    unittest.main()
