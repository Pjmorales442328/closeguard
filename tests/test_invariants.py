# tests/test_invariants.py — stdlib-only gate (AST), fail-closed, no model number becomes an amount, SoD, no unapproved post.
import ast
import sys
import unittest
from decimal import Decimal
from pathlib import Path

from core.gate import evaluate
from core.models import Approval, BankLine, LedgerLine, Proposal
from core.sod import check_approval, check_post
from datetime import date

CORE = Path(__file__).resolve().parents[1] / "core"
B = BankLine("B1", date(2026, 10, 5), Decimal("100.00"), "DR", "Acme", "ACM-10001", "SYNTHETIC")
L = LedgerLine("INV-1", "Acme", True, date(2026, 10, 1), date(2026, 10, 31), Decimal("100.00"), "ACM-10001", "6100")
BANK, LEDGER = {"B1": B}, {"INV-1": L}


def good():
    return Proposal("B1", ("INV-1",), Decimal("100.00"), {"INV-1": Decimal("100.00")}, "match")


class InvariantTest(unittest.TestCase):
    def test_core_imports_stdlib_only(self):
        for path in CORE.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text("utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module] if isinstance(node, ast.ImportFrom) else []
                for n in names:
                    root = n.split(".")[0]
                    self.assertTrue(root in sys.stdlib_module_names or root == "core", f"{path.name} imports {n}")

    def test_allow_path(self):
        self.assertEqual(evaluate(good(), BANK, LEDGER).result, "allow")

    def test_model_cannot_change_amount(self):
        p = good()
        p.amount = Decimal("1000.00")
        p.parts = {"INV-1": Decimal("1000.00")}
        self.assertEqual(evaluate(p, BANK, LEDGER).rule, "policy.amount_mismatch")

    def test_fail_closed_missing_field(self):
        p = good()
        p.amount = None
        self.assertEqual(evaluate(p, BANK, LEDGER).rule, "policy.missing_field")
        p = good()
        p.parts = "garbage"
        self.assertEqual(evaluate(p, BANK, LEDGER).result, "refuse")

    def test_fail_closed_on_exception(self):
        for junk in (None, object(), "text", {"txn_id": "B1"}):
            d = evaluate(junk, BANK, LEDGER)
            self.assertEqual((d.result, d.rule), ("refuse", "policy.missing_field"))
        self.assertEqual(check_post(None, [None]).result, "refuse")

    def test_segregation_of_duties(self):
        p = good()
        self.assertEqual(check_approval(p, Approval("B1", "agent", "controller", "approve")).rule,
                         "policy.segregation_of_duties")
        self.assertEqual(check_approval(p, Approval("B1", "Maria", "ap_clerk", "approve")).rule,
                         "policy.segregation_of_duties")
        self.assertEqual(check_approval(p, Approval("B1", "Maria", "controller", "approve")).result, "allow")

    def test_unapproved_post(self):
        p = good()
        self.assertEqual(check_post(p, []).rule, "policy.unapproved_post")
        self.assertEqual(check_post(p, [Approval("B1", "Maria", "controller", "reject")]).rule, "policy.unapproved_post")
        self.assertEqual(check_post(p, [Approval("B1", "agent", "cfo", "approve")]).rule, "policy.unapproved_post")
        self.assertEqual(check_post(p, [Approval("B1", "Lee", "cfo", "approve")]).result, "allow")

    def test_over_cap_lifted_by_cfo(self):
        big = BankLine("B2", date(2026, 10, 5), Decimal("12000.00"), "DR", "Acme", "ACM-10002", "SYNTHETIC")
        inv = LedgerLine("INV-2", "Acme", True, date(2026, 10, 1), date(2026, 10, 31), Decimal("12000.00"), "ACM-10002", "6100")
        p = Proposal("B2", ("INV-2",), big.amount, {"INV-2": big.amount}, "match")
        self.assertEqual(evaluate(p, {"B2": big}, {"INV-2": inv}).rule, "policy.over_cap")
        self.assertEqual(evaluate(p, {"B2": big}, {"INV-2": inv}, roles={"cfo"}).result, "allow")


if __name__ == "__main__":
    unittest.main()
