# app/services/scene.py — maps REAL run state to the Close Room scene: which zone each bank line's paper sits in.
from collections import Counter

from app.services import plain


def is_model(p) -> bool:
    """A real model answer; the offline bait stand-in says so in its rationale and does not count."""
    return p.rationale.startswith("model") and not p.rationale.startswith("model stand-in")

# zone -> (x0, y0, columns, dx, dy) in the SVG's 960x600 plan; scene.js reads the same numbers from data-* attrs
ZONES = {
    "bank": (34, 176, 16, 12, 8),       # statement lines arrive (replay start only)
    "desk": (300, 220, 16, 14, 16),     # on the agent's desk, waiting for the gate (replay only)
    "held": (42, 404, 26, 25, 26),      # refused by the gate, in the Held tray
    "waiting": (740, 88, 6, 18, 14),    # passed the gate, in the controller's in-tray (a pile)
    "approved": (866, 88, 6, 16, 14),   # stamped by a human
    "vault": (736, 462, 12, 20, 16),    # posted to the journal (diary)
}


def slot(zone: str, i: int) -> tuple:
    x0, y0, cols, dx, dy = ZONES[zone]
    return x0 + (i % cols) * dx, y0 + (i // cols) * dy


def zone_of(r: dict) -> str:
    if r["d"].result != "allow":
        return "held"
    return "vault" if r["posted"] else "approved" if r["approval"] else "waiting"


def _info(r: dict, zone: str) -> str:
    b, p, d = r["b"], r["p"], r["d"]
    head = f"{b.txn_id} · {float(b.amount):,.2f} · {', '.join(p.inv_ids) or 'no invoice'} · "
    if zone == "held":
        return head + f"held ({plain.short(d.rule)}): {plain.reason(d.rule, d.detail)}"
    if zone == "waiting":
        return head + "passed every check; waiting for a controller or CFO" + (f" (flagged: {plain.flag(d.flag)})" if d.flag else "")
    a = r["approval"]
    if zone == "approved":
        return head + f"approved by {a.approver} ({a.role}) at {r['approved_at']} UTC"
    return head + f"posted, approved by {a.approver} at {r['approved_at']} UTC; entry fingerprint (row hash) {', '.join(r['hashes'])}"


def tokens(rows: list) -> list:
    seen, out = Counter(), []
    for r in rows:
        z = zone_of(r)
        x, y = slot(z, seen[z])
        seen[z] += 1
        out.append({"id": r["b"].txn_id, "zone": z, "x": x, "y": y, "info": _info(r, z),
                    "flag": bool(r["d"].flag), "rule": plain.short(r["d"].rule) if r["d"].rule else ""})
    return out


PILL = {"live": "AI: live", "cached": "AI: saved answer", "fallback": "AI: saved answer, live failed", "failed": "AI: no answer",
        "skipped": "AI: not asked, limit reached"}


def model_line(run) -> dict:
    """Rail step 2 model text and a txn -> pill map, from the per-call record of THIS run (never from client.last)."""
    m = run.model or {}
    calls = m.get("calls", [])
    live = [c for c in calls if c["how"] == "live"]
    if live:
        text = f"AI asked live {len(live)} time{'s' if len(live) != 1 else ''} · {sum(c['latency_s'] for c in live):.1f} s · {sum(c['tokens'] for c in live):,} tokens"
    elif calls:
        n = sum(c["how"] != "skipped" for c in calls)
        text = f"{n} saved AI answer{'s' if n != 1 else ''} replayed"
    else:
        text = "AI off: a practice stand-in plays its part" if m.get("mode") == "offline" and not run.uploaded else "no AI used"
    skipped = sum(c["how"] == "skipped" for c in calls)
    text += f" · {skipped} line{'s' if skipped != 1 else ''} not asked (AI limit for this run reached)" if skipped else ""
    return {"text": text, "note": m.get("note", ""), "how": {c["txn"]: c["how"] for c in calls}, "mode": m.get("mode", "offline")}


def summary(run, rows: list) -> dict:
    """Counts the scene shows; every one is counted from run state."""
    z = Counter(zone_of(r) for r in rows)
    rules = Counter(plain.short(r["d"].rule) for r in rows if r["d"].result != "allow")
    sod = sum(1 for _, _, _, d in run.attempts if d.result == "refuse" and d.rule == "policy.segregation_of_duties")
    return {"zones": z, "rules": rules.most_common(), "sod_refusals": sod, "bank": len(run.bank),
            "model": sum(is_model(r["p"]) for r in rows),
            "flagged": sum(bool(r["d"].flag) for r in rows if r["d"].result == "allow"),
            "unmatched": sum(not r["p"].inv_ids for r in rows),
            "unmatched_refused": sum(not r["p"].inv_ids and r["d"].result != "allow" for r in rows),
            "m": model_line(run), "pill": PILL, "ledger": len(run.ledger), "verified": bool(run.verify and run.verify.get("match")),
            "reader": (run.verify or {}).get("reader_count"), "writer": (run.receipt or {}).get("written")}


if __name__ == "__main__":
    assert slot("held", 0) == (42, 404) and slot("held", 27) == (42 + 25, 404 + 26)
    print("ok")
