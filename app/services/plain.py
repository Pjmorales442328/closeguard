# app/services/plain.py — the ONE place that turns rule ids, field keys and gate details into plain words for people.
import calendar
import re

# rule id -> (short name for chips and tallies, plain reason used when a detail cannot be read more precisely)
RULES = {
    "policy.missing_field": ("details missing", "Something needed to pay this is missing or unreadable, so it is held."),
    "policy.amount_mismatch": ("wrong amount", "The proposed amount is not what the bank actually paid."),
    "policy.evidence_missing": ("no paperwork", "There is no matching bank line or invoice on file."),
    "policy.duplicate_payment": ("paid twice", "This invoice was already paid."),
    "policy.near_duplicate": ("looks like a repeat", "Almost the same payment went to this supplier a few days earlier."),
    "policy.unknown_payee": ("unknown payee", "The payee is not on the approved supplier list."),
    "policy.over_cap": ("over the limit", "This is over the spending limit and needs a CFO."),
    "policy.date_window": ("wrong dates", "The payment date is too far from the invoice dates."),
    "policy.period_closed": ("outside the month", "The payment is outside the month being closed."),
    "policy.split_unbalanced": ("split does not add up", "The split across invoices does not add up to the payment."),
    "policy.part_mismatch": ("part payment", "Part payments are not allowed: each invoice must be paid in full."),
    "policy.memo_instruction": ("memo gives orders", "The bank memo tries to give the agent orders. Memos are read as data, never obeyed."),
    "policy.segregation_of_duties": ("not allowed to approve", "Only a controller or CFO, and never the one who proposed it, can approve."),
    "policy.memo_unacknowledged": ("flag not read", "The approver must confirm they read the flagged memo before approving."),
    "policy.unapproved_post": ("not approved yet", "Nothing is posted until a controller or CFO approves it."),
    "intake.line_sum": ("total does not add up", "The line items do not add up to the bill total."),
    "intake.dates": ("dates wrong", "The bill dates do not make sense."),
    "intake.duplicate_invoice": ("duplicate bill", "This invoice number was already seen."),
    "intake.amount_positive": ("amount not positive", "The bill total is not more than zero."),
    "intake.currency": ("not US dollars", "Only bills in US dollars are supported."),
    "intake.vendor_known": ("supplier unreadable", "The supplier name could not be read."),
}
FIELDS = {"supplier": "supplier", "invoice_no": "invoice number", "invoice_date": "invoice date", "due_date": "due date",
          "currency": "currency", "total": "total", "line_items": "line items", "notes": "notes", "*": "whole reading"}
READERS = ("Reader 1", "Reader 2")
_N = r"(?P<{}>-?[\d.]+)"
# (rule, detail pattern, plain sentence); {names} are the pattern's groups, money groups are formatted 1,234.00
_DETAIL = [
    ("policy.part_mismatch", rf"part {_N.format('a')} for (?P<i>\S+) != invoice amount {_N.format('b')}",
     "Paid {a} against a {b} invoice ({i}): part payments are not allowed."),
    ("policy.amount_mismatch", rf"proposal amount {_N.format('a')} != bank amount {_N.format('b')}",
     "The proposal says {a} but the bank paid {b}: the amounts must match."),
    ("policy.split_unbalanced", rf"parts sum {_N.format('a')} != bank amount {_N.format('b')}",
     "The split adds up to {a} but the payment is {b}."),
    ("policy.evidence_missing", r"txn (?P<t>\S+) not in bank CSV", "Bank line {t} is not on the bank statement."),
    ("policy.evidence_missing", r"proposal cites no invoice", "No invoice could be found for this payment, so a person has to look at it."),
    ("policy.evidence_missing", r"invoice (?P<i>\S+) not in ledger CSV", "Invoice {i} is not in the books."),
    ("policy.duplicate_payment", r"invoice already paid by (?P<t>\S+)", "This invoice was already paid by bank line {t}."),
    ("policy.duplicate_payment", r"same vendor, amount and reference as (?P<t>\S+)",
     "Same supplier, amount and reference as bank line {t}: this would pay twice."),
    ("policy.near_duplicate", rf"within 1% and 3 days of (?P<t>\S+) \({_N.format('a')} on (?P<d>[\d-]+)\)",
     "Almost the same as bank line {t} ({a} on {d}) to the same supplier within 3 days: looks like a repeat payment."),
    ("policy.unknown_payee", r"invoice (?P<i>\S+) vendor not in vendor master",
     "The supplier on invoice {i} is not on the approved supplier list."),
    ("policy.unknown_payee", r"counterparty '?(?P<c>.+?)'? not in vendor master", "{c} is not on the approved supplier list."),
    ("policy.over_cap", rf"{_N.format('a')} exceeds single cap {_N.format('b')}",
     "{a} is over the {b} limit for one payment: only a CFO can approve that."),
    ("policy.over_cap", rf"vendor month total {_N.format('a')} exceeds {_N.format('b')}",
     "This supplier's total for the month would be {a}, over the {b} limit: only a CFO can approve that."),
    ("policy.date_window", r"bank date (?P<d>[\d-]+) outside .* of (?P<i>\S+)",
     "Paid on {d}, outside the allowed dates for invoice {i} (5 days before it was issued to 30 days after it was due)."),
    ("policy.period_closed", r"bank date (?P<d>[\d-]+) outside period (?P<y>\d+)-(?P<mo>\d+)",
     "Paid on {d}, which is outside the month being closed ({mo} {y})."),
    ("policy.memo_instruction", r"instruction-like text in (?P<f>\w+): .*?'(?P<h>.+?)'",
     "The bank {f} reads like an order to the agent (\"{h}\"). Memos are read as data, never obeyed."),
    ("policy.segregation_of_duties", r"approver 'agent' role '[^']*' may not approve proposal by 'agent'",
     "The agent tried to approve its own work. Blocked: only a controller or CFO can approve."),
    ("policy.segregation_of_duties", r"approver '(?P<w>[^']*)' role '(?P<r>[^']*)' may not approve proposal by '(?P=w)'",
     "{w} tried to approve their own proposal. Blocked: only a controller or CFO can approve."),
    ("policy.segregation_of_duties", r"approver '(?P<w>[^']*)' role '(?P<r>[^']*)'",
     "{w} ({r}) cannot approve: only a controller or CFO who did not propose it can."),
    ("policy.memo_unacknowledged", r"must be acknowledged by (?P<w>.+?) before",
     "{w} must tick \"I have read the flagged memos\" before approving."),
    ("intake.line_sum", rf"lines add up to {_N.format('a')}, bill total is {_N.format('b')}",
     "The line items add up to {a} but the bill total says {b}."),
    ("intake.dates", r"due date (?P<d>\S+) is before invoice date (?P<e>\S+)", "The due date ({d}) is before the invoice date ({e})."),
    ("intake.dates", r"invoice date (?P<d>\S+) is outside 2026", "The invoice date {d} is not in 2026."),
    ("intake.duplicate_invoice", r"invoice number (?P<n>.+) was already seen", "Invoice number {n} was already seen in this batch."),
    ("intake.amount_positive", rf"total {_N.format('a')} is not positive", "The total ({a}) is not more than zero."),
    ("intake.currency", r"currency (?P<c>\S+) is not USD", "The bill is in {c}; only US dollars are supported."),
]


def money(v) -> str:
    """1250 / '1250.00' -> '1,250.00'; anything else unchanged."""
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def short(rule) -> str:
    return RULES.get(rule, (str(rule or "").split(".")[-1].replace("_", " "), ""))[0]


def field(key) -> str:
    return FIELDS.get(key, str(key).replace("_", " "))


def reason(rule, detail="") -> str:
    """One plain sentence for a refusal or check: the specific numbers when the detail matches, else the rule's reason."""
    detail = str(detail or "")
    if detail.startswith("unparseable input"):
        return "Some details could not be read, so it is held to be safe."
    for r, pat, out in _DETAIL:
        m = r == rule and re.search(pat, detail)
        if m:
            g = {k: money(v) if re.fullmatch(r"-?\d+\.\d+", v or "") else v for k, v in m.groupdict().items()}
            if "mo" in g:
                g["mo"] = calendar.month_name[int(g["mo"])]
            return out.format(**g)
    return RULES.get(rule, ("", detail or "Held by a check."))[1]


def flag(text) -> str:
    """Soft memo flag 'memo: 'approve'' -> plain words."""
    m = re.match(r"(\w+): '?(.+?)'?$", str(text or ""))
    return f"the bank {m[1]} mentions \"{m[2]}\"" if m else str(text or "")


def source(text) -> str:
    """Run source line ('model (cache first, then live)', ...) -> plain words."""
    t = str(text or "")
    if "uploaded" in t:
        return "your uploaded files, exact-match rules only (no AI)"
    if "matcher only" in t:
        return "exact-match rules only (AI off or failed)"
    if "fallback" in t and "failed" in t:
        return "AI failed: a practice stand-in plays its part"
    return "AI matching on (saved answers first)" if t.startswith("model") else "AI off: a practice stand-in plays its part"


if __name__ == "__main__":
    assert reason("policy.part_mismatch", "part 1250.00 for INV-1 != invoice amount 1520.00") == \
        "Paid 1,250.00 against a 1,520.00 invoice (INV-1): part payments are not allowed."
    assert reason("policy.segregation_of_duties", "approver 'agent' role 'agent' may not approve proposal by 'agent'").startswith("The agent tried")
    assert reason("policy.over_cap", "x") == RULES["policy.over_cap"][1] and short("policy.unknown_payee") == "unknown payee"
    assert flag("memo: 'approve'") == 'the bank memo mentions "approve"' and field("invoice_no") == "invoice number"
    print("ok")
