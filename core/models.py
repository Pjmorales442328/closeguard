# core/models.py — Decimal money + the dataclasses every other module speaks in. No float, ever.
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

CENT = Decimal("0.01")
PERIOD = (2026, 10)  # the one close period the synthetic set covers


def money(v) -> Decimal:
    """Strict money parse: Decimal with at most 2 places. Floats are rejected so binary rounding never enters."""
    if isinstance(v, float):
        raise TypeError("float money is not allowed")
    try:
        d = Decimal(str(v).strip())
    except InvalidOperation:
        raise ValueError(f"bad amount {v!r}") from None
    if not d.is_finite() or d != d.quantize(CENT):
        raise ValueError(f"amount must have at most 2 decimals: {v!r}")
    return d.quantize(CENT)


@dataclass(frozen=True)
class BankLine:
    txn_id: str
    date: date
    amount: Decimal
    direction: str  # DR (money out) or CR (money in)
    counterparty: str
    reference: str
    memo: str


@dataclass(frozen=True)
class LedgerLine:
    inv_id: str
    vendor: str
    vendor_known: bool
    inv_date: date
    due_date: date
    amount: Decimal
    reference: str
    gl_account: str


@dataclass
class Proposal:
    """A proposed posting: bank line txn_id against one (match) or several (split) invoices."""
    txn_id: str
    inv_ids: tuple
    amount: Decimal
    parts: dict  # inv_id -> Decimal allocated
    kind: str  # match | split | unmatched
    rationale: str = ""
    proposer: str = "agent"


@dataclass(frozen=True)
class Decision:
    txn_id: str
    result: str  # allow | refuse
    rule: str | None
    detail: str
    flag: str | None = None  # soft memo flag on an allowed proposal ("memo: 'approved'"); approver must acknowledge


@dataclass(frozen=True)
class Approval:
    txn_id: str
    approver: str
    role: str
    decision: str  # approve | reject
    note: str = ""
    ack: bool = False  # approver has read a flagged memo/reference


@dataclass(frozen=True)
class JournalEntry:
    txn_id: str
    inv_id: str
    amount: Decimal
    debit_gl: str
    credit_gl: str
    description: str
    approver: str


def in_window(d: date, inv: LedgerLine) -> bool:
    """Policy date window: [inv_date - 5 days, due_date + 30 days]. Shared by matcher and gate."""
    return inv.inv_date - timedelta(days=5) <= d <= inv.due_date + timedelta(days=30)
