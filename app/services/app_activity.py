# app/services/app_activity.py — the audit trail as a bookkeeper reads it: who did what, in plain words, newest first.
from app import state
from app.services import bill_remove, plain

WHO = {"ana": ("Ana", "bookkeeper"), "maria": ("Maria", "approver"), "ai": ("AI", "Closeguard"), "rules": ("Rules", "fixed checks"),
       "supplier": ("Supplier", "email"), "books": ("Books", "database")}


def _supplier(bills: list) -> dict:
    out = dict(bill_remove.REMOVED)  # removed bills keep their name in the history
    for b in bills:
        bid, n = b["id"].rsplit("/", 1)
        out[(bid, int(n))] = b
    return out


def _name(names: dict, bill_id) -> str:
    try:
        bid, n = str(bill_id).rsplit("/", 1)
        return names[(bid, int(n))]
    except (ValueError, KeyError):
        return {"supplier": "a", "label": ""}


def feed(bills: list, limit: int = 40) -> list:
    names, out = _supplier(bills), []
    with state.LOCK:
        chain = list(state.CHAIN[-600:])
    for e in chain:
        p, k = e["payload"] if isinstance(e["payload"], dict) else {}, e["kind"]
        row = None
        if k == "bill_checked":
            b = _name(names, p.get("bill_id"))
            row = ("rules", f"Read the {b['supplier']} bill with two AI readers on Vultr and checked it" + (f": {b['label'].lower()}" if b["label"] else ""))
        elif k == "bill_removed":
            row = ("ana", f"Removed the {p.get('supplier')} bill {p.get('invoice_no') or ''}".rstrip() + (f" (${p.get('total')})" if p.get("total") else "") + ": it no longer counts anywhere")
        elif k in ("voice_answer", "email_consent"):
            row = ("ana", f"Answered the assistant: “{p.get('text')}”" + (" (spoken)" if p.get("heard") else ""))
        elif k == "bill_confirmed":
            row = ("maria", f"Confirmed the {_name(names, p.get('bill_id'))['supplier']} bill" if p.get("result") == "allow" else f"Tried to confirm a bill: {plain.reason(p.get('rule'), p.get('detail'))}")
        elif k == "approval":
            if p.get("role") == "agent" or p.get("approver") == "agent":
                row = ("ai", "Asked to approve a payment itself. Refused by the rules: only a named person can approve")
            elif p.get("result") == "allow":
                last = out[-1] if out else None
                if last and last["key"] == "approve":  # one line per approval click, not one per payment
                    last["n"] += 1; last["text"] = f"Approved {last['n']} payments"; continue
                out.append({"key": "approve", "n": 1, "at": e["at"], "who": "maria", "text": "Approved 1 payment"}); continue
        elif k == "pin_refused":
            row = ("rules", f"Wrong PIN for {p.get('who')} when trying to {p.get('what', 'do a money step').split(' in run')[0].split(' run ')[0]}: refused" + (", locked for a minute" if p.get("locked") else ""))
        elif k == "books_exported":
            row = ("maria", f"Exported {p.get('entries')} recorded payments for QuickBooks (PIN checked)")
        elif k == "post":
            row = ("books", f"Recorded {p.get('written')} payments as paid in the database")
        elif k == "verify_db":
            row = ("books", "Double-checked the saved payments: " + ("they match what Maria approved" if p.get("match") else "MISMATCH"))
        elif k == "email_sent":
            row = ("ana", f"Approved and sent the email “{p.get('subject')}” (demo outbox)")
        elif k == "email_followup":
            row = ("ai", f"Sent follow-up #{p.get('n')} to {p.get('to')}, on schedule (demo outbox)")
        elif k == "email_reply":
            row = ("supplier", "Replied: asks to pay a different bank account. Flagged as a possible scam, nothing changed" if p.get("scam")
                   else f"Replied; the AI read it as: {str(p.get('intent')).replace('_', ' ')}")
        elif k == "supplier_locked":
            row = ("rules", f"Locked {p.get('supplier')}: they asked to change bank details. No payment until Maria calls back")
        elif k == "supplier_called_back":
            row = ("maria", f"Called {p.get('supplier')} back on the number on file: bank details unchanged, lock lifted (PIN checked)")
        elif k == "evidence_downloaded":
            row = ("maria", "Downloaded the month's proof from Vultr Object Storage (PIN checked)")
        elif k == "evidence_saved":
            row = ("maria", f"Saved the month's proof ({p.get('files')} files, {max(1, int(p.get('bytes') or 0) // 1024)} KB) to Vultr Object Storage")
        if row:
            out.append({"key": k, "at": e["at"], "who": row[0], "text": row[1]})
    return [{"at": r["at"], "who": WHO[r["who"]][0], "role": WHO[r["who"]][1], "kind": r["who"], "text": r["text"]} for r in out[-limit:]][::-1]
