# tests/test_intake_merge.py — per-field merge of two readings: picks, typed values, locked agreed fields, strict errors.
import unittest

from core.intake_checks import IntakeError, normalise
from core.intake_merge import merge, show

RAW = {"supplier": "Birch Logistics", "invoice_no": "BIR-1", "invoice_date": "2026-10-03", "due_date": "2026-11-02",
       "currency": "USD", "total": "30.00", "line_items": ["10.00", "20.00"], "notes": ""}
A = normalise(RAW)
B = normalise({**RAW, "invoice_no": "BIR-7", "due_date": "2026-11-07"})


class MergeTest(unittest.TestCase):
    def test_picks_come_from_the_chosen_reader_and_agreed_fields_are_locked(self):
        m, src = merge(A, B, ["invoice_no", "due_date"], {"invoice_no": "1", "due_date": "0", "total": "other:1.00"})
        self.assertEqual((m.invoice_no, str(m.due_date), str(m.total)), ("BIR-7", "2026-11-02", "30.00"))
        self.assertEqual(src, {"invoice_no": "reader B", "due_date": "reader A"})

    def test_typed_value_uses_the_normaliser(self):
        m, src = merge(A, B, ["invoice_no"], {"invoice_no": "other:bir 9"})
        self.assertEqual((m.invoice_no, src["invoice_no"]), ("BIR-9", "typed"))
        m, _ = merge(A, normalise({**RAW, "line_items": ["5.00", "25.00"]}), ["line_items"], {"line_items": "other: 12.50 + 17.50"})
        self.assertEqual(show(m, "line_items"), "12.50 + 17.50")

    def test_missing_unknown_or_invalid_picks_raise(self):
        for diffs, picks in ((["invoice_no"], {}), (["invoice_no"], {"invoice_no": "2"}), (["invoice_no"], {"invoice_no": "other:"}),
                             (["due_date"], {"due_date": "other:03/11/2026"}), (["total"], {"total": "other:1.234"}),
                             (["nope"], {"nope": "0"})):
            with self.assertRaises(IntakeError, msg=(diffs, picks)):
                merge(A, B, diffs, picks)


if __name__ == "__main__":
    unittest.main()
