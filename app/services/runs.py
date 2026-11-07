# app/services/runs.py — one close run: load CSVs, match, propose, gate, hash-chain every event.
import time
import uuid

from app import config, state
from app.services.proposals import cross_check, get_proposals
from core.csvload import load_bank, load_ledger
from core.gate import run_gate
from core.matcher import match
from core.models import PERIOD


def _event(p, d) -> dict:
    return {"txn_id": p.txn_id, "inv_ids": list(p.inv_ids), "amount": str(p.amount), "kind": p.kind,
            "proposer": p.proposer, "result": d.result, "rule": d.rule, "detail": d.detail, "flag": d.flag}


def create_seed_run(live: bool = False) -> state.Run:
    return create_run(load_bank(config.BANK_CSV), load_ledger(config.LEDGER_CSV), live=live)


def create_run(bank: list, ledger: list, uploaded: bool = False, live: bool = False, standin: bool = True) -> state.Run:
    """Uploaded data never reaches the model (cost guard) and never gets the synthetic baits."""
    t0 = time.perf_counter()
    if uploaded:
        proposals, source = match(bank, ledger), "deterministic matcher only (uploaded data; model is off for uploads)"
        meta = {"mode": "offline", "calls": [], "note": ""}
    else:
        proposals, source, meta = get_proposals(match(bank, ledger), bank, ledger, live, standin)
    bank_d, ledger_d = {b.txn_id: b for b in bank}, {l.inv_id: l for l in ledger}
    decisions = {d.txn_id: d for d in run_gate(proposals, bank_d, ledger_d, PERIOD)}
    if not uploaded:
        decisions = cross_check(decisions, proposals, bank_d, ledger_d)
    rid = uuid.uuid4().hex[:16] if uploaded else uuid.uuid4().hex[:8]  # uploaded runs: unguessable link
    run = state.Run(rid, bank_d, ledger_d, proposals, decisions, source, 0.0, uploaded=uploaded, model=meta)
    with state.LOCK:
        state.log("run_created", {"run_id": run.id, "bank_lines": len(bank), "ledger_rows": len(ledger),
                                  "source": source, "synthetic": not uploaded,
                                  "model_mode": meta["mode"], "model_calls": meta["calls"]})
        for p in proposals:
            state.log("gate_decision", {"run_id": run.id, **_event(p, decisions[p.txn_id])})
        run.seconds = time.perf_counter() - t0
        state.RUNS[run.id] = run
    return run


def get_run(run_id: str):
    return state.RUNS.get(run_id)


def rows(run: state.Run) -> list:
    """View rows for the proposals table, in bank order."""
    approved = {a.txn_id: a for a in run.approvals}
    out = []
    for p in run.proposals:
        b, d = run.bank[p.txn_id], run.decisions[p.txn_id]
        out.append({"p": p, "b": b, "d": d, "inv": [run.ledger[i] for i in p.inv_ids if i in run.ledger],
                    "ghosts": [i for i in p.inv_ids if i not in run.ledger],
                    "approval": approved.get(p.txn_id), "approved_at": run.approved_at.get(p.txn_id),
                    "posted": p.txn_id in run.posted, "hashes": run.row_hashes.get(p.txn_id, [])})
    return out
