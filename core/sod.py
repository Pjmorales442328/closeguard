# core/sod.py — rules 13-14: segregation of duties on approval, flagged memos need an acknowledgement, no post
# without a valid approval. Fail closed.
from core.gate import APPROVER_ROLES, _closed, _up
from core.models import Decision


def check_approval(p, a, flag=None) -> Decision:  # rule 13
    """flag = the gate decision's soft memo flag (if any): the approver must set ack=True to approve a flagged line."""
    def run():
        if _up(a.approver) == _up(p.proposer) or a.role.strip().lower() not in APPROVER_ROLES:
            return Decision(p.txn_id, "refuse", "policy.segregation_of_duties",
                            f"approver {a.approver!r} role {a.role!r} may not approve proposal by {p.proposer!r}")
        if flag and a.ack is not True:
            return Decision(p.txn_id, "refuse", "policy.memo_unacknowledged",
                            f"flagged text ({flag}) must be acknowledged by {a.approver} before approval")
        return Decision(p.txn_id, "allow", None, f"approved by {a.approver} ({a.role})" + (" after reading the flag" if flag else ""))
    return _closed(getattr(p, "txn_id", "?"), run)


def check_post(p, approvals, flag=None) -> Decision:  # rule 14
    def run():
        ok = [a for a in approvals if a.txn_id == p.txn_id and a.decision == "approve"
              and check_approval(p, a, flag).result == "allow"]
        if not ok:
            return Decision(p.txn_id, "refuse", "policy.unapproved_post", "no valid controller/cfo approval on file")
        return Decision(p.txn_id, "allow", None, f"post authorised by {ok[0].approver}")
    return _closed(getattr(p, "txn_id", "?"), run)
