# tests/test_matcher.py — deterministic matcher hit rate on the synthetic set (target >= 60/80).
import json
import unittest
from pathlib import Path

from core.csvload import load_bank, load_ledger
from core.matcher import match

SYN = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def load():
    bank, ledger = load_bank(SYN / "bank_2026-10.csv"), load_ledger(SYN / "ledger_2026-10.csv")
    faults = json.loads((SYN / "faults.json").read_text("utf-8"))
    return bank, ledger, faults


class MatcherTest(unittest.TestCase):
    def test_hit_rate(self):
        bank, ledger, faults = load()
        props = match(bank, ledger)
        self.assertEqual([p.txn_id for p in props], [b.txn_id for b in bank])
        hits = [p for p in props if p.kind != "unmatched"]
        print(f"\nmatcher: {len(hits)}/{len(bank)} matched deterministically")
        self.assertGreaterEqual(len(hits), 60)
        baited = {f["txn_id"] for f in faults["faults"] if f["bait"]}
        self.assertEqual({p.txn_id for p in props if p.kind == "unmatched"}, baited)

    def test_tricky_legit_matched(self):
        bank, ledger, faults = load()
        by_txn = {p.txn_id: p for p in match(bank, ledger)}
        for t in faults["legit_tricky"]:
            self.assertNotEqual(by_txn[t].kind, "unmatched", t)

    def test_kinds(self):
        bank, ledger, faults = load()
        kinds = {p.txn_id: p.kind for p in match(bank, ledger)}
        for f in faults["faults"]:
            if f["type"] == "split_unbalanced":
                self.assertEqual(kinds[f["txn_id"]], "split")


if __name__ == "__main__":
    unittest.main()
