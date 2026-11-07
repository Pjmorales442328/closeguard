# tests/test_gate.py — all 30 planted faults refused with the expected rule; zero false refusals on legit lines.
import json
import unittest
from collections import Counter
from decimal import Decimal

from core.gate import run_gate
from core.matcher import match
from core.models import Proposal
from tests.test_matcher import load


def deterministic_proposals():
    """Matcher output, with the bait proposals from faults.json standing in for the model on unmatched lines."""
    bank, ledger, faults = load()
    props = {p.txn_id: p for p in match(bank, ledger)}
    for f in faults["faults"]:
        if f["bait"]:
            inv, amt = tuple(f["bait"]["inv_ids"]), Decimal(f["bait"]["amount"])
            props[f["txn_id"]] = Proposal(f["txn_id"], inv, amt, dict.fromkeys(inv, amt), "match", "model bait")
    return bank, ledger, faults, [props[b.txn_id] for b in bank]


class GateAcceptanceTest(unittest.TestCase):
    def test_all_30_faults_refused_with_expected_rule(self):
        bank, ledger, faults, props = deterministic_proposals()
        decisions = {d.txn_id: d for d in run_gate(props, {b.txn_id: b for b in bank}, {l.inv_id: l for l in ledger})}
        rows, misses = [], []
        for f in faults["faults"]:
            d = decisions[f["txn_id"]]
            rows.append((f["id"], f["txn_id"], f.get("expect_bait", f["expect"]), d.rule))
            if d.rule != f.get("expect_bait", f["expect"]):
                misses.append(rows[-1])
        print("\n" + "\n".join(f"{i} {t} {e} -> {g}" for i, t, e, g in rows))
        self.assertEqual(misses, [])

    def test_zero_false_refusals_on_legit_lines(self):
        bank, ledger, faults, props = deterministic_proposals()
        fault_ids = {f["txn_id"] for f in faults["faults"]}
        decisions = run_gate(props, {b.txn_id: b for b in bank}, {l.inv_id: l for l in ledger})
        bad = [(d.txn_id, d.rule, d.detail) for d in decisions if d.txn_id not in fault_ids and d.result != "allow"]
        allowed = Counter(d.result for d in decisions)
        print(f"\ngate: {allowed['allow']} allowed, {allowed['refuse']} refused of {len(decisions)}")
        self.assertEqual(bad, [])
        self.assertEqual(allowed["refuse"], 30)


if __name__ == "__main__":
    unittest.main()


class PartMismatchTest(unittest.TestCase):
    def test_partial_payment_refused_even_when_amount_equals_bank(self):
        """The real model proposed B0078 as a 1250.00 partial of the 1520.00 invoice INV-2037; amount == bank passes
        rule 2, so rule 11 must catch the short-pay. The deterministic bait (1520.00) still trips amount_mismatch."""
        bank, ledger, faults, props = deterministic_proposals()
        partial = Proposal("B0078", ("INV-2037",), Decimal("1250.00"), {"INV-2037": Decimal("1250.00")}, "match", "model")
        ctx = ({b.txn_id: b for b in bank}, {l.inv_id: l for l in ledger})
        d = run_gate([partial], *ctx)[0]
        self.assertEqual((d.result, d.rule), ("refuse", "policy.part_mismatch"))
        self.assertIn("1250.00", d.detail)
        bait = next(p for p in props if p.txn_id == "B0078")
        self.assertEqual(run_gate([bait], *ctx)[0].rule, "policy.amount_mismatch")
