# app/services/app_bank.py — the bank statement tab of the bookkeeper app: each October payment ticked off against a scanned bill.
from dataclasses import replace
from decimal import Decimal

from app import state
from app.services import plain

LAST_RUN: dict = {"id": None}  # the newest match of the scanned bills against the bank; cleared by Clear


def rematch():
    """Match every scanned bill against the bank statement again, right after each scan or confirm (no button).
    Deterministic matcher + gate; the model is not called (live=False), so this costs nothing."""
    from app.services import intake, stage_job  # late import, stage_job calls this
    cards = []
    for bid, n in list(stage_job.SCANNED):
        b = intake.get(bid)
        c = next((c for c in b.cards if c.n == n), None) if b else None
        if c is not None:
            cards.append((b, c))
    from app.services import bank_import
    if bank_import.rows() is None or not any(c.status in ("ready", "confirmed") for _, c in cards):  # no statement yet: nothing to match
        LAST_RUN["id"] = None
        return None
    batch = intake.Batch(f"stage{len(state.CHAIN)}", [replace(c, n=i) for i, (_, c) in enumerate(cards, 1)],  # unique BILL-nnn ids
                         any(b.uploaded for b, _ in cards))
    run = intake.make_run(batch, None)
    LAST_RUN["id"] = run.id
    return run


def _line(b, run, held) -> dict:
    row = {"txn": b.txn_id, "date": str(b.date), "who": b.counterparty, "ref": b.reference, "amount": plain.money(b.amount),
           "kind": "wait", "text": "Waiting for its bill: scan it to match"}
    p = run and next((p for p in run.proposals if p.txn_id == b.txn_id), None)
    seen = held.get(b.reference)
    if not p and seen and seen[0] in ("hold", "check"):  # before the match: the scanned bill already says this payment needs a look
        return {**row, "kind": seen[0], "text": ("Its bill is on hold: " + seen[3]) if seen[0] == "hold" else "Its bill needs a person to check it"}
    if not p:
        return row
    d = run.decisions[p.txn_id]
    inv = [run.ledger[i] for i in p.inv_ids if i in run.ledger]
    if d.result == "allow":
        return {**row, "kind": "pay", "text": "Matches the bill " + ", ".join(f"{x.reference} from {x.vendor}" for x in inv)}
    if not inv and seen and seen[0] == "pay" and seen[2] != plain.money(b.amount):  # bill passed, but the bank paid another amount
        return {**row, "kind": "hold", "text": f"Amount differs: the bill says ${seen[2]}, the bank paid ${row['amount']}"}
    if not inv and seen and seen[0] != "pay":  # the bill was scanned but did not pass: say why, not "no bill"
        k = seen[0]
        return {**row, "kind": "hold", "text": "Its bill still needs a person to check it" if k == "check" else "Its bill is on hold, so this payment needs a look"}
    if not inv:
        return {**row, "kind": "wait", "text": "Waiting for its bill: scan it to match"}
    if d.rule == "policy.duplicate_payment":
        first = next((x for x in run.bank.values() if x.reference == b.reference and x.txn_id != b.txn_id), None)
        return {**row, "kind": "hold", "text": "Paid twice: this bill was already paid" + (f" on {first.date:%b} {first.date.day}" if first else "")}
    if d.rule == "policy.unknown_payee":
        return {**row, "kind": "hold", "text": f"{b.counterparty} is not on the approved supplier list"}
    return {**row, "kind": "hold", "text": plain.reason(d.rule, d.detail)}


def held_map(bills) -> dict:
    return {x["invoice_no"]: (x["kind"], x["label"], x["total"], (x["note"] or "").rstrip(".")) for x in bills if x["invoice_no"]}


def lines_for(run, bills=()) -> dict:
    """txn id -> plain line for one run (the pay screen says the same thing as the bank tab)."""
    held = held_map(bills)
    return {b.txn_id: _line(b, run, held) for b in run.bank.values()}


def view(bills=()) -> dict:
    """Bank lines in date order with their match status, and the totals a bookkeeper checks at month end.
    bills = the app's scanned bills, so a payment whose bill is on hold or unchecked says so."""
    held = held_map(bills)
    run = state.RUNS.get(LAST_RUN["id"] or "")
    from app.services import bank_import
    bank = run.bank.values() if run else (bank_import.rows() or [])
    pairs = [(b, _line(b, run, held)) for b in sorted(bank, key=lambda b: (b.date, b.txn_id))]
    lines = [x for _, x in pairs]
    total = sum((b.amount for b, _ in pairs), Decimal(0))
    ok = sum((b.amount for b, x in pairs if x["kind"] == "pay"), Decimal(0))
    refs = {b.reference for b in bank}
    unpaid = [{"who": x["supplier"], "ref": x["invoice_no"], "total": x["total"], "kind": x["kind"], "note": x["note"]}
              for x in bills if x["kind"] in ("hold", "check") and x["invoice_no"] and x["invoice_no"] not in refs]  # held, and no money went out
    return {"imported": bank_import.rows() is not None, "source": bank_import.name(), "unpaid_held": unpaid, "matched": run is not None, "run": LAST_RUN["id"], "lines": lines, "count": len(lines), "ok": sum(x["kind"] == "pay" for x in lines),
            "total": plain.money(total), "ok_total": plain.money(ok), "gap": plain.money(total - ok)}
