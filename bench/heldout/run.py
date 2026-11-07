# bench/heldout/run.py — `python -m bench.heldout.run`: blind held-out attacks + realistic legit memos through the gate.
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from agent.client import Client
from agent.propose import propose
from bench.run import SYN, _offline
from core.csvload import load_bank, load_ledger
from core.gate import evaluate, run_gate
from core.matcher import match
from core.models import PERIOD

HERE = Path(__file__).resolve().parent


def load(name, d=HERE):
    return json.loads((d / name).read_text("utf-8"))


def base_case():
    """Same path as bench/run.py: matcher + cached model + gate; returns the first allowed proposal and its world."""
    bank, ledger = load_bank(SYN / "bank_2026-10.csv"), load_ledger(SYN / "ledger_2026-10.csv")
    bmap, lmap = {b.txn_id: b for b in bank}, {l.inv_id: l for l in ledger}
    proposals = propose(match(bank, ledger), bank, ledger, Client(call=_offline))
    decisions = run_gate(proposals, bmap, lmap, PERIOD)
    p = next(p for p, d in zip(proposals, decisions) if d.result == "allow")
    return p, bmap, lmap


def trial(p, bmap, lmap, **fields):
    b = dict(bmap)
    b[p.txn_id] = replace(b[p.txn_id], **fields)
    return evaluate(p, b, lmap, PERIOD)


def run(data=HERE) -> dict:
    p, bmap, lmap = base_case()
    passes, flagged, refusals, legit_flags, cls = [], [], [], [], {}
    for a in load("attacks.json", data):
        c = cls.setdefault(a["cls"], Counter())
        trials = [("memo+reference", {"memo": a["text"], "reference": a["ref"]})] if "ref" in a else \
                 [(f, {f: a["text"]}) for f in ("memo", "reference")]
        for field, kw in trials:
            d = trial(p, bmap, lmap, **kw)
            k = "blocked" if d.result == "refuse" else "flagged" if d.flag else "passed"
            c[k] += 1
            if k != "blocked":
                (flagged if k == "flagged" else passes).append(
                    {"id": a["id"], "cls": a["cls"], "field": field, "text": a["text"], "flag": d.flag,
                     **({"ref": a["ref"]} if "ref" in a else {})})
    legit = load("legit.json", data)
    for g in legit:
        for f in ("memo", "reference"):
            d = trial(p, bmap, lmap, **{f: g["text"]})
            if d.result == "refuse":
                refusals.append({"id": g["id"], "field": f, "text": g["text"], "rule": d.rule, "detail": d.detail})
            elif d.flag:
                legit_flags.append({"id": g["id"], "field": f, "text": g["text"], "flag": d.flag})
    at = sum(sum(c.values()) for c in cls.values())
    ab, af = sum(c["blocked"] for c in cls.values()), sum(c["flagged"] for c in cls.values())
    return {"synthetic": True, "base_txn": p.txn_id,
            "attacks": {"strings": len(load("attacks.json", data)), "trials": at, "blocked": ab, "flagged": af,
                        "passed": at - ab - af, "block_rate": round(ab / at, 4), "unflagged_rate": round((at - ab - af) / at, 4),
                        "classes": {k: {"blocked": v["blocked"], "flagged": v["flagged"], "passed": v["passed"]}
                                    for k, v in sorted(cls.items())},
                        "passes": passes, "flagged_list": flagged},
            "legit": {"strings": len(legit), "trials": 2 * len(legit), "refused": len(refusals),
                      "lines_refused": len({r["id"] for r in refusals}), "flagged": len(legit_flags),
                      "lines_flagged": len({r["id"] for r in legit_flags}), "clean": 2 * len(legit) - len(refusals) - len(legit_flags),
                      "false_refusal_rate": round(len(refusals) / (2 * len(legit)), 4), "refusals": refusals,
                      "flags": legit_flags}}


def md(r) -> str:
    a, g = r["attacks"], r["legit"]
    out = ["# Held-out memo-rule test (synthetic, blind)", "",
           f"Base proposal {r['base_txn']}; each string placed in memo and, separately, reference (split class: both at once).", "",
           f"**Attacks:** {a['blocked']}/{a['trials']} trials hard-blocked ({a['block_rate']:.1%}), {a['flagged']} flagged for "
           f"the approver, **{a['passed']} passed unflagged** ({a['unflagged_rate']:.1%}); {a['strings']} strings.",
           f"**Legit:** {g['refused']}/{g['trials']} trials falsely refused ({g['false_refusal_rate']:.1%}, "
           f"{g['lines_refused']}/{g['strings']} memos); {g['flagged']} flagged ({g['lines_flagged']}/{g['strings']} memos); "
           f"{g['clean']} clean.", "",
           "| class | hard-blocked | flagged | passed unflagged |", "|---|---|---|---|"]
    out += [f"| {k} | {v['blocked']} | {v['flagged']} | {v['passed']} |" for k, v in a["classes"].items()]
    out += ["", "## Every attack that passed unflagged", ""]
    out += [f"- {x['id']} [{x['cls']}] {x['field']}: `{json.dumps(x['text'] + (' || ' + x['ref'] if 'ref' in x else ''), ensure_ascii=False)[:160]}`"
            for x in a["passes"]] or ["- none"]
    out += ["", "## Every attack that was only flagged (allowed, approver must acknowledge)", ""]
    out += [f"- {x['id']} [{x['cls']}] {x['field']}: `{json.dumps(x['text'], ensure_ascii=False)[:120]}` -> {x['flag']}"
            for x in a["flagged_list"]] or ["- none"]
    out += ["", "## Every false refusal", ""]
    out += [f"- {x['id']} {x['field']}: `{x['text']}` -> {x['rule']}: {x['detail']}" for x in g["refusals"]] or ["- none"]
    out += ["", "## Every legit memo that was flagged", ""]
    out += [f"- {x['id']} {x['field']}: `{x['text']}` -> {x['flag']}" for x in g["flags"]] or ["- none"]
    return "\n".join(out) + "\n"


def main(data=HERE):
    r = run(data)
    (data / "results.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    (data / "results.md").write_text(md(r), encoding="utf-8", newline="\n")
    a, g = r["attacks"], r["legit"]
    print(f"attacks {a['blocked']}/{a['trials']} hard-blocked, {a['flagged']} flagged, {a['passed']} passed unflagged; "
          f"legit {g['refused']}/{g['trials']} refused, {g['flagged']} flagged, {g['clean']} clean")


if __name__ == "__main__":
    main()
