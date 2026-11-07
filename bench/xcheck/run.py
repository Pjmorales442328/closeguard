# bench/xcheck/run.py — `python -m bench.xcheck.run [--live]`: the second model reviews every match the first model
# proposed in bench/e2e (3 bait lines, 97 set-B injection variants, controls) plus the 3 seed narratives.
import argparse
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from agent import client as ac, xcheck
from agent.client import Client
from agent.propose import narrate
from bench import cost
from bench.e2e.run import HERE as E2E, NEUTRAL_REF, world
from bench.run import _offline
from core.gate import run_gate
from core.models import PERIOD, Proposal

HERE = Path(__file__).resolve().parent
MAX_CALLS = 60


class Budget:
    """Counts every real attempt (retries too) and hard-stops at MAX_CALLS; offline it only replays the cache."""
    def __init__(self, live):
        self.n, self.live = 0, live

    def __call__(self, model, messages, max_tokens):
        if not self.live:
            return _offline(model, messages, max_tokens)
        if self.n >= MAX_CALLS:
            raise RuntimeError("xcheck call budget exhausted")
        self.n += 1
        return ac._openai_call(model, messages, max_tokens)


def proposal(txn, parts: dict) -> Proposal:
    parts = {k: Decimal(v) for k, v in parts.items()}
    return Proposal(txn, tuple(parts), sum(parts.values(), Decimal(0)), parts, "split" if len(parts) > 1 else "match",
                    "model confidence (first model; hidden from the second)")


def run(live=False) -> dict:
    bmap, lmap, free, base = world()
    e2e = json.loads((E2E / "results.json").read_text("utf-8"))
    budget = Budget(live)
    c = xcheck.client(call=budget, backoff=2.0 if live else 0, retries=3 if live else 1)
    rows = []
    for t in e2e["trials"]:
        if t["kind"] == "unmatched" or t["kind"] == "error":
            continue  # nothing was proposed, so there is nothing for a second model to agree with
        b = replace(bmap[t["line"]], **t["text"])
        v = xcheck.review(c, b, free, proposal(t["line"], t["parts"]))
        rows.append({"id": t["id"], "cls": t["cls"], "line": t["line"], "field": t["field"], "parts": t["parts"],
                     "gate": t["gate"], **v, "usage": c.last.get("usage"), "latency_s": c.last.get("latency_s"),
                     "cached": c.last.get("cached")})
    controls = []
    for name, reps in e2e["controls"].items():
        for r in reps:
            if r["kind"] == "unmatched":
                continue
            b = bmap[name.split("|")[0]]
            b = replace(b, reference=NEUTRAL_REF) if "|reference" in name else b
            v = xcheck.review(c, b, free, proposal(b.txn_id, r["parts"]))
            controls.append({"control": name, "repeat": r["repeat"], "parts": r["parts"], **v,
                             "usage": c.last.get("usage"), "latency_s": c.last.get("latency_s")})
    decisions = run_gate(base, bmap, lmap, PERIOD)
    allowed = [p for p, d in zip(base, decisions) if d.result == "allow"][:3]  # same sample as agent/seed_run.py
    narr = narrate(allowed, list(bmap.values()), list(lmap.values()), Client(call=_offline))
    narratives = []
    for p in allowed:
        v = xcheck.review_narrative(c, bmap[p.txn_id], [lmap[i] for i in p.inv_ids], narr[p.txn_id])
        narratives.append({"txn_id": p.txn_id, "inv_ids": list(p.inv_ids), "narrative": narr[p.txn_id], **v,
                           "usage": c.last.get("usage"), "latency_s": c.last.get("latency_s")})
    n = len(rows)
    agree = sum(r["agree"] for r in rows)
    caught = [r for r in rows if not r["agree"] and r["gate"]["result"] == "allow"]
    return {"synthetic": True, "first_model": e2e["model"], "second_model": xcheck.XCHECK_MODEL,
            "real_calls_this_run": budget.n, "candidates_shown": [l.inv_id for l in free],
            "e2e_trials": len(e2e["trials"]), "reviewed": n, "agree": agree, "disagree": n - agree,
            "agreement_rate": round(agree / n, 3) if n else None,
            "gate_refused_all_reviewed": all(r["gate"]["result"] == "refuse" for r in rows),
            "disagreements_on_gate_allowed": len(caught), "trials": rows, "controls": controls,
            "narratives": narratives, "cost": cost.summarize(c.history, 0, 0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help=f"allow real second-model calls on cache miss (budget {MAX_CALLS})")
    r = run(ap.parse_args().live)
    (HERE / "results.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(json.dumps({k: r[k] for k in ("second_model", "real_calls_this_run", "reviewed", "agree", "disagree",
                                        "disagreements_on_gate_allowed")}))


if __name__ == "__main__":
    main()
