# app/services/plain_entry.py — one plain sentence per audit-trail entry, for the /ledger page (raw payload stays beside it).
from app.services.plain import field, reason


def _gate(p):
    if p.get("result") == "refuse":
        return f"Held {p.get('txn_id')}: {reason(p.get('rule'), p.get('detail'))}"
    return f"{p.get('txn_id')} passed every check" + (" (memo flagged for the approver)" if p.get("flag") else "")


def _approval(p):
    if p.get("result") == "allow":
        return f"{p.get('approver')} ({p.get('role')}) approved {p.get('txn_id')}"
    return f"{p.get('approver')} ({p.get('role')}) was blocked from approving {p.get('txn_id')}: {reason(p.get('rule'), p.get('detail'))}"


def _bill(p, verb):
    if p.get("result") == "allow":
        return f"{p.get('who')} ({p.get('role')}) {verb} bill {p.get('bill_id')}"
    return f"{p.get('who')} ({p.get('role')}) was blocked on bill {p.get('bill_id')}: {reason(p.get('rule'), p.get('detail'))}"


TEXT = {
    "run_created": lambda p: f"Close started: {p.get('bank_lines')} bank lines, {p.get('ledger_rows')} invoices",
    "gate_decision": _gate,
    "approval": _approval,
    "post": lambda p: f"Posted {p.get('written')} entries to the books",
    "verify_db": lambda p: f"Double-checked: all {p.get('reader_count')} entries saved exactly as approved" if p.get("match")
    else f"Double-check FAILED: {p.get('reader_count')} of {p.get('writer_count')} entries read back, and they differ",
    "bill_received": lambda p: f"Bill photo received: {p.get('name')}",
    "bill_read": lambda p: f"Bill {p.get('bill_id')} read by an AI reader" + (" (saved answer)" if p.get("cached") else ""),
    "bill_checked": lambda p: f"Bill {p.get('bill_id')} checked: " + (
        f"the readers disagree on {', '.join(field(f) for f in p['diffs'])}" if p.get("diffs") else f"status {p.get('status')}"),
    "bill_confirmed": lambda p: _bill(p, "confirmed"),
    "bill_rejected": lambda p: _bill(p, "rejected"),
    "intake_run": lambda p: f"Close started from {len(p.get('bill_ids') or [])} checked bills",
    "voice_query": lambda p: f"Question asked: \"{p.get('text')}\"",
}


def entry(kind: str, payload: dict) -> str:
    """Plain words for one chain entry; never raises (an odd payload shows its kind)."""
    try:
        return TEXT[kind](payload)
    except Exception:  # noqa: BLE001 — display only; the raw payload is still shown
        return kind.replace("_", " ")


if __name__ == "__main__":
    assert entry("post", {"written": 53}) == "Posted 53 entries to the books"
    assert entry("gate_decision", {"txn_id": "B1", "result": "refuse", "rule": "policy.duplicate_payment",
                                   "detail": "invoice already paid by B0"}).endswith("already paid by bank line B0.")
    assert entry("nope", {}) == "nope"
    print("ok")
