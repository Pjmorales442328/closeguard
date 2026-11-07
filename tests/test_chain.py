# tests/test_chain.py — chain verifies clean; any tampered byte is reported at the first bad seq.
import copy
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from core.chain import append, load, save, verify


def chain(n=5):
    entries = []
    for i in range(n):
        append(entries, "gate.refuse" if i % 2 else "proposal", {"txn_id": f"B{i}", "amount": Decimal("1.10")},
               at="2026-10-31T00:00:00+00:00")
    return entries


class ChainTest(unittest.TestCase):
    def test_verify_ok(self):
        self.assertEqual(verify(chain()), {"ok": True, "length": 5, "first_bad_seq": None})
        self.assertTrue(verify([])["ok"])

    def test_tamper_payload(self):
        c = chain()
        c[2]["payload"]["amount"] = "9.99"
        self.assertEqual(verify(c)["first_bad_seq"], 3)

    def test_tamper_hash_and_reorder(self):
        c = chain()
        c[4]["hash"] = "0" * 64
        self.assertEqual(verify(c)["first_bad_seq"], 5)
        c = chain()
        c[1], c[2] = c[2], c[1]
        self.assertEqual(verify(c)["first_bad_seq"], 2)
        c = chain()
        del c[3]  # removing an entry breaks the link at the next one
        self.assertEqual(verify(c)["first_bad_seq"], 4)

    def test_copy_tamper_leaves_original_intact(self):
        c = chain()
        bad = copy.deepcopy(c)
        bad[0]["kind"] = "post"
        self.assertEqual(verify(bad)["first_bad_seq"], 1)
        self.assertTrue(verify(c)["ok"])

    def test_roundtrip_file(self):
        c = chain()
        with tempfile.TemporaryDirectory() as t:
            save(Path(t) / "ledger.jsonl", c)
            back = load(Path(t) / "ledger.jsonl")
        self.assertTrue(verify(back)["ok"])
        self.assertEqual([e["hash"] for e in back], [e["hash"] for e in c])
        self.assertEqual(load(Path("does/not/exist.jsonl")), [])


if __name__ == "__main__":
    unittest.main()
