# app/state.py — process-local run store and the single audit hash chain (demo scale; one uvicorn worker).
import threading
from dataclasses import dataclass, field

from core import chain

LOCK = threading.Lock()  # one global lock; per-run locks only if many judges hit at once
RUNS: dict = {}
CHAIN: list = []


@dataclass
class Run:
    id: str
    bank: dict  # txn_id -> BankLine (bank order preserved)
    ledger: dict  # inv_id -> LedgerLine
    proposals: list
    decisions: dict  # txn_id -> Decision
    source: str  # where proposals came from (model live / deterministic fallback)
    seconds: float
    approvals: list = field(default_factory=list)  # accepted Approval objects
    attempts: list = field(default_factory=list)  # every approval attempt: (txn_id, approver, role, Decision)
    posted: set = field(default_factory=set)
    approved_at: dict = field(default_factory=dict)  # txn_id -> chain timestamp of the accepted approval
    row_hashes: dict = field(default_factory=dict)  # txn_id -> [journal row_hash] from the writer receipt
    receipt: dict | None = None
    verify: dict | None = None
    store: str = ""
    uploaded: bool = False  # judge CSV upload: memory only, never posted to Postgres
    model: dict = field(default_factory=dict)  # {mode: live|cache|offline, calls: [{txn, how, latency_s, tokens}], note}

    def counters(self) -> dict:
        res = [d.result for d in self.decisions.values()]
        return {"bank lines": len(self.bank), "proposed": sum(bool(p.inv_ids) for p in self.proposals),
                "allowed": res.count("allow"), "refused": res.count("refuse"),
                "approved": len({a.txn_id for a in self.approvals}), "posted": len(self.posted),
                "seconds": f"{self.seconds:.2f}"}


def log(kind: str, payload) -> dict:
    """Append one event to the audit chain. Caller holds LOCK."""
    return chain.append(CHAIN, kind, payload)
