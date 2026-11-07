# app/services/trick.py — "Try to trick it": visitor text replaces one real memo; the FULL gate + SoD + post checks decide.
import hashlib
from dataclasses import replace
from datetime import datetime, timezone

from app.services import attempts
from core.gate import run_gate
from core.models import PERIOD, Approval
from core.sod import check_approval, check_post

MAX_MEMO = 2000


def try_memo(run, memo: str) -> dict:
    """Re-gates the first gate-allowed proposal with the memo swapped in. Read-only: the run is not changed."""
    memo = (memo or "")[:MAX_MEMO]
    p = next((p for p in run.proposals if run.decisions[p.txn_id].result == "allow"), None)
    if p is None:
        return {"memo": memo, "txn_id": None, "result": "refuse", "rule": None, "detail": "no allowed proposal to test"}
    bank = dict(run.bank)
    bank[p.txn_id] = replace(bank[p.txn_id], memo=memo)
    # whole run through the gate so duplicate/near-duplicate history is the same as in the real run
    d = next(x for x in run_gate(run.proposals, bank, run.ledger, PERIOD) if x.txn_id == p.txn_id)
    self_ok = check_approval(p, Approval(p.txn_id, p.proposer, "agent", "approve"))
    post = check_post(p, [])  # what happens if this proposal tries to post before a human approves
    out = {"memo": memo, "txn_id": p.txn_id, "result": d.result, "rule": d.rule, "detail": d.detail, "flag": d.flag,
           "outcome": "blocked" if d.result == "refuse" else "flagged" if d.flag else "passed",
           "self_approval": self_ok, "post_without_approval": post,
           "unacked": check_approval(p, Approval(p.txn_id, "Maria", "controller", "approve"), d.flag)}
    attempts.record({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run_id": run.id,
                     "txn_id": None if run.uploaded else p.txn_id, "memo_sha256": hashlib.sha256(memo.encode()).hexdigest()[:16],
                     "memo_len": len(memo), "gate": d.result, "rule": d.rule, "flag": d.flag,
                     "self_approval": self_ok.result, "post_without_approval": post.result})
    return out
