# core/intake_checks.py — bill-reading checks: strict normalise, two-reader agreement, fail-closed deterministic rules.
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from core.models import Decision, LedgerLine, money

YEAR = (date(2026, 1, 1), date(2026, 12, 31))
FIELDS = ("supplier", "invoice_no", "invoice_date", "due_date", "currency", "total", "line_items")


class IntakeError(ValueError):
    """A reading that does not match the schema. The caller treats it as 'unreadable', never as a partial bill."""


@dataclass(frozen=True)
class Bill:
    supplier: str
    invoice_no: str
    invoice_date: date
    due_date: date
    currency: str
    total: Decimal
    line_items: tuple  # sorted Decimal amounts
    notes: str = field(default="", compare=False)  # free text: display only, never compared or trusted


def _text(v, name) -> str:
    if not isinstance(v, str) or not v.strip():
        raise IntakeError(f"{name} missing")
    return " ".join(v.split())


def _day(v, name) -> date:
    try:
        return date.fromisoformat(_text(v, name))
    except ValueError:
        raise IntakeError(f"{name} is not YYYY-MM-DD") from None


def _amount(v, name) -> Decimal:
    if isinstance(v, bool) or not isinstance(v, (str, int, Decimal)):  # floats are rejected on purpose
        raise IntakeError(f"{name} is not an exact amount")
    try:
        return money(v)
    except (ValueError, TypeError) as e:
        raise IntakeError(f"{name}: {e}") from None


def supplier_key(s: str) -> str:
    return re.sub(r"[\W_]+", " ", s.casefold()).strip()


def ref_key(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def normalise(raw) -> Bill:
    """Raw model dict -> Bill, or IntakeError. Floats must already be Decimal/str (see agent.extract)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("line_items"), list):
        raise IntakeError("not an object with line_items")
    lines = [_amount(it.get("amount") if isinstance(it, dict) else it, f"line {i + 1}")
             for i, it in enumerate(raw["line_items"])]
    return Bill(_text(raw.get("supplier"), "supplier"), "-".join(_text(raw.get("invoice_no"), "invoice_no").upper().split()),
                _day(raw.get("invoice_date"), "invoice_date"), _day(raw.get("due_date"), "due_date"),
                _text(raw.get("currency"), "currency").upper(), _amount(raw.get("total"), "total"), tuple(sorted(lines)),
                str(raw.get("notes") or "")[:500])


def _cmp(b: Bill) -> dict:
    return {**{f: getattr(b, f) for f in FIELDS}, "supplier": supplier_key(b.supplier), "invoice_no": ref_key(b.invoice_no)}


def agree(a: Bill, b: Bill) -> list:
    """Names of structured fields where the two readings differ. Empty = agreed. `notes` never counts."""
    x, y = _cmp(a), _cmp(b)
    return [f for f in FIELDS if x[f] != y[f]]


def _line_sum(b, refs):
    if sum(b.line_items, Decimal(0)) != b.total:
        return f"lines add up to {sum(b.line_items, Decimal(0))}, bill total is {b.total}"


def _dates(b, refs):
    if b.invoice_date > b.due_date:
        return f"due date {b.due_date} is before invoice date {b.invoice_date}"
    if not YEAR[0] <= b.invoice_date <= YEAR[1]:
        return f"invoice date {b.invoice_date} is outside 2026"


def _duplicate(b, refs):
    if ref_key(b.invoice_no) in refs:
        return f"invoice number {b.invoice_no} was already seen"


def _positive(b, refs):
    if b.total <= 0:
        return f"total {b.total} is not positive"


def _currency(b, refs):
    if b.currency != "USD":
        return f"currency {b.currency} is not USD"


CHECKS = [("line_sum", _line_sum), ("dates", _dates), ("duplicate_invoice", _duplicate), ("amount_positive", _positive),
          ("currency", _currency)]


def known_vendor(supplier: str, vendors) -> str | None:
    """Canonical vendor name for a supplier string, or None when the vendor master does not list it."""
    return next((v for v in vendors if supplier_key(v) == supplier_key(supplier)), None)


def check(bill, seen_refs=frozenset(), vendors=(), bill_id="?") -> list:
    """One Decision per rule. Any exception = refuse. Unknown supplier is a flag (allow), the payment gate refuses later."""
    out = []
    for name, fn in CHECKS:
        try:
            detail = fn(bill, seen_refs)
            out.append(Decision(bill_id, "refuse" if detail else "allow", f"intake.{name}" if detail else None, detail or "ok"))
        except Exception as e:  # noqa: BLE001 — fail closed, like core.gate
            out.append(Decision(bill_id, "refuse", f"intake.{name}", f"unparseable input: {e!r}"))
    try:
        ok = known_vendor(bill.supplier, vendors) is not None
        out.append(Decision(bill_id, "allow", None, "supplier is on the vendor list" if ok else "supplier not on vendor list",
                            None if ok else "unknown supplier"))
    except Exception as e:  # noqa: BLE001
        out.append(Decision(bill_id, "refuse", "intake.vendor_known", f"unparseable input: {e!r}"))
    return out


def failed(decisions) -> list:
    return [d for d in decisions if d.result == "refuse"]


def to_ledger_line(bill: Bill, n: int, vendors, gl) -> LedgerLine:
    v = known_vendor(bill.supplier, vendors)
    return LedgerLine(f"BILL-{n:03d}", v or bill.supplier, v is not None, bill.invoice_date, bill.due_date, bill.total,
                      bill.invoice_no, gl.get(v, "6999"))
