# bench/intake.py — scores the two bill readers on the 12 synthetic bills from the committed cache (offline) -> intake.json/md.
# Run: python -m bench.intake   (add --readme to refresh the table block in README.md between the intake markers)
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent import extract
from app.services import intake_read as ir
from core.intake_checks import FIELDS, agree, failed, normalise
from core.models import Decision

ROOT = Path(__file__).resolve().parent.parent
BILLS = ROOT / "data" / "synthetic" / "bills"
OUT = ROOT / "bench" / "results"
BEGIN, END = "<!-- intake:begin -->", "<!-- intake:end -->"


def _caught(card, truth, trap):
    """-> layer that handled the bill: check:<rule> | confirm | flag:vendor_known | read_ok (text changed nothing) | none."""
    if card.status == "refused":
        bad = next((d for i in card.checks for d in failed(card.checks[i])), Decision("", "refuse", "unknown", ""))
        return f"check:{bad.rule.split('.')[-1]}"
    if card.status == "confirm":
        return "confirm"
    flagged = any(d.flag for ds in card.checks.values() for d in ds)
    if trap == "unknown_supplier" and flagged:
        return "flag:vendor_known"
    if trap in ("instruction", "scan") and all(b and not agree(truth, b) for b in card.readings):
        return "read_ok"
    return "none"


def run() -> dict:
    os.environ["CG_MODEL_LIVE"] = "0"  # offline on purpose: the numbers must come from the committed cache
    manifest = json.loads((BILLS / "manifest.json").read_text("utf-8"))["bills"]
    cards, per = [], {m: {"right": 0, "unreadable": 0, "lat": [], "p": 0, "c": 0} for m in extract.MODELS}
    for n, m in enumerate(manifest, 1):
        data = (BILLS / m["file"]).read_bytes()
        card = ir.Card(n, m["file"], "image/jpeg", data, "", f"bench/{n:02d}")
        ir.read_card(card, ir.seen_refs(cards, card))
        cards.append(card)
        truth = normalise(m["truth"])
        for i, model in enumerate(extract.MODELS):
            s, meta = per[model], card.metas[i]
            if card.readings[i] is None:
                s["unreadable"] += 1
                continue
            s["right"] += len(FIELDS) - len(agree(truth, card.readings[i]))
            s["lat"].append(meta.get("latency_s") or 0)
            s["p"] += (meta.get("usage") or {}).get("prompt", 0)
            s["c"] += (meta.get("usage") or {}).get("completion", 0)
    n = len(manifest)
    traps = [{"id": m["file"][:3], "trap": m["trap"], "caught_by": _caught(c, normalise(m["truth"]), m["trap"])}
             for m, c in zip(manifest, cards) if m["trap"] != "clean"]
    agreed = [c for c in cards if c.status != "unreadable" and not c.diffs]
    wrong = [m["file"] for m, c in zip(manifest, cards) if c in agreed and agree(normalise(m["truth"]), c.readings[0])]
    return {"synthetic": True, "bills": n, "traps": len(traps), "fields": list(FIELDS),
            "per_model": {k: {"field_acc": round(v["right"] / ((n - v["unreadable"]) * len(FIELDS) or 1), 4),
                              "unreadable": v["unreadable"], "mean_latency_s": round(sum(v["lat"]) / max(len(v["lat"]), 1), 2),
                              "tokens": {"prompt": v["p"], "completion": v["c"]}} for k, v in per.items()},
            "agreement": {"agreed": len(agreed), "confirm_queue": n - len(agreed)},
            "agreed_but_wrong": wrong, "statuses": {m["file"]: c.status for m, c in zip(manifest, cards)},
            "traps_detail": traps, "traps_caught": sum(t["caught_by"] != "none" for t in traps),
            "clean_passed": sum(c.status == "ready" for m, c in zip(manifest, cards) if m["trap"] == "clean"),
            "clean_bills": sum(m["trap"] == "clean" for m in manifest),
            "calls": 2 * n, "cached": sum(bool(c.metas[i].get("cached")) for c in cards for i in (0, 1)),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def markdown(r: dict) -> str:
    pm, rows = r["per_model"], []
    for k, v in pm.items():
        rows.append(f"| {k} | {v['field_acc'] * 100:.1f}% | {v['unreadable']} | {v['mean_latency_s']} s | "
                    f"{v['tokens']['prompt']} / {v['tokens']['completion']} |")
    t = "".join(f"| {d['id']} | {d['trap']} | {d['caught_by']} |\n" for d in r["traps_detail"])
    return (f"Measured on {r['bills']} synthetic bills ({r['traps']} with planted traps), {r['calls']} model calls "
            f"({r['cached']} read from the committed cache).\n\n| reader | field accuracy ({len(r['fields'])} fields) | unreadable | mean latency | tokens in / out |\n"
            f"|---|---|---|---|---|\n" + "\n".join(rows) + f"\n\nThe two readers agreed on {r['agreement']['agreed']} of {r['bills']} bills "
            f"({r['agreement']['confirm_queue']} go to a human or are refused); {r['clean_passed']} of {r['clean_bills']} clean bills "
            f"pass; traps handled by a layer: {r['traps_caught']} of {r['traps']}. Agreed but wrong: {len(r['agreed_but_wrong'])}.\n\n"
            f"| bill | trap | handled by |\n|---|---|---|\n{t}")


def main() -> None:
    r = run()
    OUT.mkdir(exist_ok=True)
    (OUT / "intake.json").write_text(json.dumps(r, indent=1), "utf-8", newline="\n")
    md = markdown(r)
    (OUT / "intake.md").write_text(md, "utf-8", newline="\n")
    if "--readme" in sys.argv:
        p = ROOT / "README.md"
        s = p.read_text("utf-8")
        a, b = s.index(BEGIN) + len(BEGIN), s.index(END)
        p.write_text(s[:a] + "\n" + md + s[b:], "utf-8", newline="\n")
    print(md)


if __name__ == "__main__":
    main()
