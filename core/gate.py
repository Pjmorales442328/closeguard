# core/gate.py — POLICY GATE. Stdlib only, fail closed. The model proposes; this module disposes.
from decimal import Decimal
from typing import NamedTuple

from core.models import CENT, Decision, in_window
from core.rules_memo import memo_instruction
from core.rules_memo_flag import memo_flag
from core.rules_parts import part_mismatch

SINGLE_CAP = Decimal("10000.00")
VENDOR_CAP = Decimal("25000.00")
APPROVER_ROLES = {"controller", "cfo"}


class Ctx(NamedTuple):
    bank: dict  # txn_id -> BankLine
    ledger: dict  # inv_id -> LedgerLine
    period: tuple  # (year, month)
    prior: list  # proposals already allowed in this run
    roles: frozenset  # approval roles already granted for this proposal


def _up(s): return str(s).strip().upper()  # noqa: E704


def missing_field(p, c):
    for f in ("txn_id", "inv_ids", "amount", "parts", "kind"):
        if getattr(p, f, None) is None or getattr(p, f) == "":
            return f"missing {f}"
    if not isinstance(p.amount, Decimal) or p.amount != p.amount.quantize(CENT):
        return "amount is not a Decimal with 2 places"
    if set(p.parts) != set(p.inv_ids) or any(not isinstance(v, Decimal) for v in p.parts.values()):
        return "parts must cover exactly the cited invoices with Decimal amounts"


def amount_mismatch(p, c):
    b = c.bank.get(p.txn_id)
    if b and p.amount != b.amount:
        return f"proposal amount {p.amount} != bank amount {b.amount}"


def evidence_missing(p, c):
    if p.txn_id not in c.bank:
        return f"txn {p.txn_id} not in bank CSV"
    if not p.inv_ids:
        return "proposal cites no invoice"
    ghosts = [i for i in p.inv_ids if i not in c.ledger]
    if ghosts:
        return f"invoice {ghosts[0]} not in ledger CSV"


def duplicate_payment(p, c):
    b = c.bank[p.txn_id]
    for q in c.prior:
        qb = c.bank[q.txn_id]
        if set(q.inv_ids) & set(p.inv_ids):
            return f"invoice already paid by {q.txn_id}"
        if (_up(qb.counterparty), qb.amount, _up(qb.reference)) == (_up(b.counterparty), b.amount, _up(b.reference)):
            return f"same vendor, amount and reference as {q.txn_id}"


def near_duplicate(p, c):
    b = c.bank[p.txn_id]
    for q in c.prior:
        qb = c.bank[q.txn_id]
        if (_up(qb.counterparty) == _up(b.counterparty) and _up(qb.reference) != _up(b.reference)
                and abs(qb.amount - b.amount) <= max(qb.amount, b.amount) * Decimal("0.01")
                and abs((qb.date - b.date).days) <= 3):
            return f"within 1% and 3 days of {q.txn_id} ({qb.amount} on {qb.date})"


def unknown_payee(p, c):
    master = {_up(l.vendor) for l in c.ledger.values() if l.vendor_known}
    for i in p.inv_ids:
        if not c.ledger[i].vendor_known:
            return f"invoice {i} vendor not in vendor master"
    cp = c.bank[p.txn_id].counterparty
    if _up(cp) not in master:
        return f"counterparty {cp!r} not in vendor master"


def over_cap(p, c):
    if "cfo" in c.roles:
        return None
    if p.amount > SINGLE_CAP:
        return f"{p.amount} exceeds single cap {SINGLE_CAP} without CFO approval"
    cp = _up(c.bank[p.txn_id].counterparty)
    total = p.amount + sum((q.amount for q in c.prior if _up(c.bank[q.txn_id].counterparty) == cp), Decimal(0))
    if total > VENDOR_CAP:
        return f"vendor month total {total} exceeds {VENDOR_CAP} without CFO approval"


def date_window(p, c):
    b = c.bank[p.txn_id]
    for i in p.inv_ids:
        if not in_window(b.date, c.ledger[i]):
            return f"bank date {b.date} outside [inv_date-5, due_date+30] of {i}"


def period_closed(p, c):
    d = c.bank[p.txn_id].date
    if (d.year, d.month) != tuple(c.period):
        return f"bank date {d} outside period {c.period[0]}-{c.period[1]:02d}"


def split_unbalanced(p, c):
    total = sum(p.parts.values(), Decimal(0))
    if total != p.amount:
        return f"parts sum {total} != bank amount {p.amount}"


RULES = [missing_field, amount_mismatch, evidence_missing, duplicate_payment, near_duplicate, unknown_payee,
         over_cap, date_window, period_closed, split_unbalanced, part_mismatch, memo_instruction]


def _closed(txn, fn):
    """Fail closed: any exception inside a rule is a refusal, never a pass."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — deliberately broad
        return Decision(str(txn), "refuse", "policy.missing_field", f"unparseable input: {e!r}")


def evaluate(p, bank: dict, ledger: dict, period=(2026, 10), prior=(), roles=frozenset()) -> Decision:
    def run():
        c = Ctx(bank, ledger, period, list(prior), frozenset(roles))
        for rule in RULES:
            detail = rule(p, c)
            if detail:
                return Decision(p.txn_id, "refuse", "policy." + rule.__name__, detail)
        return Decision(p.txn_id, "allow", None, f"passed {len(RULES)} rules", memo_flag(p, c))
    return _closed(getattr(p, "txn_id", "?"), run)


def run_gate(proposals, bank: dict, ledger: dict, period=(2026, 10), roles=frozenset()) -> list:
    """Evaluate in order; earlier allowed proposals become the prior state for duplicate and cap rules."""
    allowed, out = [], []
    for p in proposals:
        d = evaluate(p, bank, ledger, period, allowed, roles)
        out.append(d)
        if d.result == "allow":
            allowed.append(p)
    return out
