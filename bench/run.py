# bench/run.py — `python -m bench.run [--gate off] [--live]`: matcher + cached model + gate over the synthetic set.
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.client import Client
from agent.propose import narrate, propose
from bench import attacks, cost, faults, report
from core.csvload import load_bank, load_ledger
from core.gate import run_gate
from core.matcher import match
from core.models import PERIOD, Decision

ROOT = Path(__file__).resolve().parents[1]
SYN, OUT = ROOT / "data" / "synthetic", ROOT / "bench" / "results"
HUMAN_BASELINE = "estimate, not yet measured (bench/baseline.md); not measured by this run"


def _offline(model, messages, max_tokens):
    raise RuntimeError("bench is offline: cache miss for " + model)


def run(gate: str = "on", live: bool = False) -> dict:
    t_full = time.perf_counter()
    bank, ledger = load_bank(SYN / "bank_2026-10.csv"), load_ledger(SYN / "ledger_2026-10.csv")
    fj = json.loads((SYN / "faults.json").read_text("utf-8"))
    bmap, lmap = {b.txn_id: b for b in bank}, {l.inv_id: l for l in ledger}
    client = Client(call=None if live else _offline)

    t0 = time.perf_counter()
    before = match(bank, ledger)
    det_match = time.perf_counter() - t0
    proposals = propose(before, bank, ledger, client)
    n_unmatched = sum(p.kind == "unmatched" for p in before)
    t0 = time.perf_counter()
    decisions = run_gate(proposals, bmap, lmap, PERIOD)
    det_gate = time.perf_counter() - t0
    allowed = [p for p, d in zip(proposals, decisions) if d.result == "allow"]
    narrate(allowed[:3], bank, ledger, client)  # same sample as agent/seed_run.py so the cache replays
    dmap = {d.txn_id: d for d in decisions}
    abl = faults.ablation(fj["faults"], proposals)
    if gate == "off":  # ablation only: everything with an invoice goes to the controller
        dmap = {p.txn_id: Decision(p.txn_id, "allow" if p.inv_ids else "refuse", None, "gate off") for p in proposals}
    atk = attacks.run_attacks(proposals, decisions, bmap, lmap)
    unavailable = [p.txn_id for p in proposals if p.rationale.startswith("model unavailable")]
    return {"synthetic": True, "seed": fj["seed"], "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": client.models[0], "model_mode": "live" if live else "cache replay (offline)", "gate": gate,
            "model_unavailable_txns": unavailable, "faults": faults.fault_rows(fj["faults"], dmap),
            "metrics": faults.metrics(fj["faults"], dmap), "ablation": abl,
            "proposals": {"matcher": len(bank) - n_unmatched, "model_asked": n_unmatched,
                          "allowed": len(allowed), "refused": len(decisions) - len(allowed)},
            "cost": cost.summarize(client.history, n_unmatched, len(allowed)),
            "timing": {"deterministic_s": round(det_match + det_gate, 4), "matcher_s": round(det_match, 4),
                       "gate_s": round(det_gate, 4), "full_run_s": round(time.perf_counter() - t_full, 3)},
            "human_baseline": HUMAN_BASELINE, "attacks": atk}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", choices=["on", "off"], default="on")
    ap.add_argument("--live", action="store_true", help="allow real model calls on cache miss (needs VULTR_INFERENCE_KEY)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    r = run(a.gate, a.live)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "before.json").exists():  # frozen pre-hardening run, kept so the README can show the change honestly
        r["attacks_before"] = json.loads((out / "before.json").read_text("utf-8"))["attacks"]
    name = "latest" if a.gate == "on" else "gate_off"
    (out / f"{name}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    (out / f"{'summary' if a.gate == 'on' else 'summary_gate_off'}.md").write_text(report.render(r), encoding="utf-8", newline="\n")
    m, k = r["metrics"], r["attacks"]
    print(f"gate {a.gate}: faults refused {m['tp']}/{m['faults']}, false refusals {m['fp']}, "
          f"ablation {r['ablation']['faulty_proposals_reaching_controller']}, attacks {k['blocked']}/{k['total']} blocked, "
          f"cost ${r['cost']['measured']['usd']:.4f}, {r['timing']['full_run_s']} s -> {out / (name + '.json')}")


if __name__ == "__main__":
    main()
