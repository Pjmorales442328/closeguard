# core/matcher.py — deterministic bank->ledger matching. It proposes; it never decides (the gate does).
import re

from core.models import BankLine, LedgerLine, Proposal, in_window

REF_RE = re.compile(r"[A-Z]{3}-\d{5}")  # vendor invoice numbers as they appear in bank references


def _proposal(b: BankLine, rows, how: str) -> Proposal:
    return Proposal(b.txn_id, tuple(r.inv_id for r in rows), b.amount, {r.inv_id: r.amount for r in rows},
                    "split" if len(rows) > 1 else "match", how)


def _by_reference(b: BankLine, by_ref: dict):
    """Every reference token must resolve. A single invoice must also equal the amount; splits are left to the gate."""
    refs = REF_RE.findall(b.reference.upper())
    rows = [by_ref[r] for r in refs if r in by_ref]
    if not refs or len(rows) != len(refs):
        return None
    if len(rows) == 1 and rows[0].amount != b.amount:
        return None
    return _proposal(b, rows, "exact reference " + " ".join(refs))


def _unique(b: BankLine, cands, how: str):
    return _proposal(b, cands, how) if len(cands) == 1 else None


def _by_amount_date(b: BankLine, free: dict):
    cands = [l for l in free.values() if l.amount == b.amount and in_window(b.date, l)]
    return _unique(b, cands, "amount and date window")


def _by_payee_amount(b: BankLine, free: dict):
    cands = [l for l in free.values() if l.amount == b.amount and l.vendor.upper() == b.counterparty.upper()]
    return _unique(b, cands, "payee and amount")


def match(bank: list, ledger: list) -> list:
    """One Proposal per bank line, in bank order. Unmatched lines are what the model will be asked about."""
    by_ref = {l.reference.upper(): l for l in ledger}
    free = {l.inv_id: l for l in ledger}  # invoices not yet claimed by a fuzzy rule
    out = []
    for b in bank:
        p = _by_reference(b, by_ref) or _by_amount_date(b, free) or _by_payee_amount(b, free)
        if p is None:
            p = Proposal(b.txn_id, (), b.amount, {}, "unmatched", "no deterministic match")
        for i in p.inv_ids:
            free.pop(i, None)
        out.append(p)
    return out
