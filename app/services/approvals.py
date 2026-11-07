# app/services/approvals.py — human approval: gate refusals stay refused; SoD (core.sod) decides who may approve.
from app import state
from app.services import bank_lock
from core.models import Approval, Decision
from core.sod import check_approval


def locked_vendor(run: state.Run, p) -> str:
    """The first supplier on this payment (any invoice of a split) that is locked after a bank-change request, '' if none."""
    return next((run.ledger[i].vendor for i in p.inv_ids if i in run.ledger and bank_lock.locked(run.ledger[i].vendor)), "")


def _one(run: state.Run, p, approver: str, role: str, ack: bool) -> Decision:
    gate = run.decisions[p.txn_id]
    if gate.result != "allow":
        return Decision(p.txn_id, "refuse", gate.rule, f"gate refused this proposal: {gate.detail}")
    a = Approval(p.txn_id, approver.strip(), role.strip().lower(), "approve", ack=ack)
    d = check_approval(p, a, gate.flag)  # who may approve comes first; a flagged memo needs the approver's acknowledgement
    vendor = d.result == "allow" and locked_vendor(run, p)
    if vendor:  # asked to change bank details: no approval until Maria has called back
        return Decision(p.txn_id, "refuse", bank_lock.RULE, f"{vendor} asked to change bank details; call them back on the number on file first")
    if d.result == "allow" and all(x.txn_id != p.txn_id for x in run.approvals):
        run.approvals.append(a)
    return d


def approve(run: state.Run, txn_id: str, approver: str, role: str, ack: bool = False) -> list:
    """txn_id '*' = every gate-allowed, not-yet-approved proposal. Every attempt is chained, refusals included."""
    done = {a.txn_id for a in run.approvals}
    if txn_id == "*":
        targets = [p for p in run.proposals if run.decisions[p.txn_id].result == "allow" and p.txn_id not in done]
    else:
        targets = [p for p in run.proposals if p.txn_id == txn_id]
    out = []
    with state.LOCK:
        for p in targets:
            d = _one(run, p, approver, role, ack)
            run.attempts.append((p.txn_id, approver, role, d))
            e = state.log("approval", {"run_id": run.id, "txn_id": p.txn_id, "approver": approver, "role": role,
                                   "ack": ack, "result": d.result, "rule": d.rule, "detail": d.detail})
            if d.result == "allow":
                run.approved_at.setdefault(p.txn_id, e["at"])
            out.append(d)
    return out
