# app/services/intake_human.py — the human step on a bill: SoD, per-field picks merged and re-checked, everything chained.
from decimal import Decimal

from agent import extract
from app import state
from app.services import intake_read as ir, plain
from core.intake_checks import IntakeError, check, failed
from core.intake_merge import merge, show
from core.models import Approval, Decision, Proposal
from core.sod import check_approval
from data.world import VENDORS

WHOLE = ["one reader unreadable"]  # only one reading exists: the human accepts or rejects that reading as a whole


def _sod(card, who: str, role: str) -> Decision:
    """Same segregation-of-duties rule as payment approval: the agent never confirms, only controller/cfo do."""
    p = Proposal(card.bill_id, (), Decimal(0), {}, "unmatched", proposer="agent")
    return check_approval(p, Approval(card.bill_id, who.strip(), role.strip().lower(), "approve"))


def _resolve(batch, card, picks: dict):
    """-> (Decision, merged Bill|None, {field: source}). Re-runs every check on the merged bill before it can enter the ledger."""
    refuse = lambda rule, detail: (Decision(card.bill_id, "refuse", rule, detail), None, {})  # noqa: E731
    try:
        if card.diffs == WHOLE:
            i = int(picks.get("*", "-1"))
            if i not in card.passing:
                return refuse("intake.checks_failed", "that reading cannot be used")
            merged, src = card.readings[i], {"*": extract.MODELS[i]}
        else:
            merged, src = merge(card.readings[0], card.readings[1], card.diffs, picks)
            src = {f: (extract.MODELS[0] if s == "reader A" else extract.MODELS[1] if s == "reader B" else s) for f, s in src.items()}
    except (IntakeError, ValueError) as e:
        return refuse("intake.pick_invalid", str(e))
    bad = failed(check(merged, ir.seen_refs(batch.cards, card), VENDORS, card.bill_id))
    if bad:
        return refuse("intake.checks_failed", "the final bill fails a check: " + " ".join(f"{plain.reason(d.rule, d.detail)} ({d.rule})" for d in bad))
    return Decision(card.bill_id, "allow", None, "merged bill passes all checks"), merged, src


def decide(batch, card, who: str, role: str, picks: dict, kind: str) -> Decision:
    d, merged, src = _sod(card, who, role), None, {}
    open_states = ("confirm", "ready") if kind == "bill_rejected" else ("confirm",)
    if d.result == "allow" and card.status not in open_states:
        d = Decision(card.bill_id, "refuse", "intake.not_waiting", f"bill is {card.status}, not waiting for this")
    if d.result == "allow" and kind == "bill_confirmed":
        d, merged, src = _resolve(batch, card, picks)
    with state.LOCK:
        state.log(kind, {"bill_id": card.bill_id, "who": who, "role": role, "result": d.result, "rule": d.rule,
                         "detail": d.detail, "picks": {k: v[:60] for k, v in picks.items()},
                         "values": {f: show(merged, f) for f in src if f != "*"} if merged else {}, "sources": src})
        if d.result == "allow":
            card.status, card.by = ("confirmed", who) if kind == "bill_confirmed" else ("rejected", who)
            card.merged, card.sources = merged, src
        card.notice = "" if d.result == "allow" else f"{plain.reason(d.rule, d.detail)} ({d.rule})"
    return d


def confirm(b, card, who, role, picks: dict) -> Decision:
    return decide(b, card, who, role, picks, "bill_confirmed")


def reject(b, card, who, role) -> Decision:
    return decide(b, card, who, role, {}, "bill_rejected")
