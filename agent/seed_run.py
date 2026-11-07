# agent/seed_run.py — one real model run over the synthetic set's unmatched lines; fills agent/cache, prints metrics.
import json
from pathlib import Path

from agent.client import Client
from agent.propose import narrate, propose
from core.csvload import load_bank, load_ledger
from core.gate import run_gate
from core.matcher import match

SYN = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def main():
    bank, ledger = load_bank(SYN / "bank_2026-10.csv"), load_ledger(SYN / "ledger_2026-10.csv")
    expect = {f["txn_id"]: f["expect"] for f in json.loads((SYN / "faults.json").read_text("utf-8"))["faults"]}
    c, calls = Client(), []
    before = match(bank, ledger)
    out = propose(before, bank, ledger, c)
    asked = [p for p0, p in zip(before, out) if p0.kind == "unmatched"]
    for p, meta in zip(asked, c.history):
        calls.append({"txn_id": p.txn_id, **meta, "proposed": [p.kind, list(p.inv_ids), str(p.amount), p.rationale]})
    decisions = run_gate(out, {b.txn_id: b for b in bank}, {l.inv_id: l for l in ledger})
    by = {d.txn_id: d for d in decisions}
    for r in calls:
        d = by[r["txn_id"]]
        r["gate"] = [d.result, d.rule, d.detail, "expected " + expect.get(r["txn_id"], "allow")]
    allowed = [p for p, d in zip(out, decisions) if d.result == "allow" and p.proposer == "agent"][:3]
    narr = narrate(allowed, bank, ledger, c)
    for p, meta in zip(allowed, c.history[len(asked):]):
        calls.append({"txn_id": p.txn_id, **meta, "narrative": narr[p.txn_id]})
    for r in calls:
        r.pop("content", None)
    print(json.dumps({"allowed": sum(d.result == "allow" for d in decisions), "refused": sum(d.result == "refuse" for d in decisions),
                      "calls": calls}, indent=1))


if __name__ == "__main__":
    main()
