# app/services/desk.py — Guard Desk: runs one scanned bill through intake and turns the card into readers, stamps, captions.
from agent import extract
from app import state
from app.services import intake, plain, runs

FIELDS = ("supplier", "invoice_no", "invoice_date", "due_date", "currency", "total", "line_items")
STAMPS = {"line_sum": ("total adds up", "total does not add up"), "dates": ("dates fine", "dates wrong"),
          "duplicate_invoice": ("not a duplicate", "duplicate invoice"), "amount_positive": ("amount positive", "amount not positive"),
          "currency": ("currency USD", "currency not USD"), "vendor_known": ("known supplier", "unknown supplier")}
LABEL = {"ready": "all checks pass", "confirm": "needs a person", "refused": "on hold", "unreadable": "unreadable", "received": "reading"}
SAMPLES = ("B02", "B07", "B09")


def latest_run():
    """The run the guard answers close questions from: newest in memory, else a fresh offline seed run."""
    return next(reversed(list(state.RUNS.values())), None) or runs.create_seed_run()


def scan(name: str, data: bytes) -> dict:
    """Raises intake.IntakeRefused (wrong type / too big). Blocks until both readers answered (a few seconds)."""
    b = intake.receive([(name, data)])
    intake.read_all(b)
    return view(b, b.cards[0])


def _val(r, f):
    v = getattr(r, f)
    return " + ".join(map(plain.money, v)) if f == "line_items" else plain.money(v) if f == "total" else str(v)


def view(b, c) -> dict:
    i = next(iter(c.checks), None)
    stamps = []
    for key, d in zip(STAMPS, c.checks.get(i) or []):  # check() returns one Decision per rule, in STAMPS order
        bad = d.result == "refuse" or bool(d.flag)
        stamps.append({"text": STAMPS[key][bad], "ok": not bad})
    readers = [{"name": plain.READERS[k], "tech": extract.MODELS[k], "ok": bool(c.readings[k]), "error": c.errors[k],
                "fields": [{"f": f, "label": plain.field(f), "v": _val(c.readings[k], f), "diff": f in c.diffs} for f in FIELDS]
                if c.readings[k] else []}
               for k in (0, 1)]
    bad = [s["text"] for s in stamps if not s["ok"]]
    diffs = " and ".join(plain.field(f) for f in c.diffs)
    head = {"refused": f"{', '.join(bad).capitalize()}." + (f" The two readers also disagree on the {diffs}." if diffs else ""),
            "confirm": f"Needs a person: the two readers disagree on the {diffs}.", "ready": "All checks pass."}.get(c.status, "")
    return {"headline": head, "id": f"{b.id}/{c.n}", "batch": b.id, "n": c.n, "status": c.status, "label": LABEL.get(c.status, c.status),
            "diffs": list(c.diffs), "readers": readers, "stamps": stamps,
            "why": [plain.reason(d.rule, d.detail) for d in c.checks.get(i) or [] if d.result == "refuse"],
            "reason": next((r["error"] for r in readers if r["error"]), "")}


def lookup(bill_id: str):
    """'batch/n' -> view dict or None. The desk only reads; confirming is intake's own form."""
    try:
        bid, n = bill_id.rsplit("/", 1)
        b = intake.get(bid)
        c = next(c for c in b.cards if c.n == int(n))
    except (ValueError, AttributeError, StopIteration):
        return None
    return view(b, c)


def bill_answer(v: dict, why: bool) -> str:
    """Spoken answer built only from the card: readings, diffs and the stamps (no model)."""
    if v["status"] == "unreadable":
        return f"I could not read this bill: {v['reason'] or 'both readers failed'}."
    ra, rb = v["readers"]
    if why:
        parts, bad = [], [s["text"] for s in v["stamps"] if not s["ok"]]
        for f in v["diffs"]:
            get = lambda r: next((x["v"] for x in r["fields"] if x["f"] == f), "nothing")
            who = "They also disagree" if parts else "The two readers disagree"
            parts.append(f"{who} on the {plain.field(f)}: one read {get(ra)}, the other {get(rb)}.")
        if v["status"] == "refused":
            parts.append(("The checks also fail. " if parts else "") + " ".join(v.get("why") or [", ".join(bad) + "."]) + " So this bill is on hold.")
        elif v["status"] == "confirm":
            parts.append("A person must look at the photo and pick the right value." + (f" Also: {', '.join(bad)}." if bad else ""))
        elif v["status"] == "ready":
            parts.append("Both readers agree and all checks pass. That is not proof it is correct: both could be wrong the same way.")
        return " ".join(parts) or v["headline"]
    r = next((x for x in v["readers"] if x["ok"]), None)
    get = lambda f: next((x["v"] for x in r["fields"] if x["f"] == f), "?")
    if v["diffs"] and "total" in v["diffs"]:
        return "The two readers disagree on the total, so I will not say a number. A person must confirm it."
    return f"Supplier {get('supplier')}, invoice number {get('invoice_no')}, total {plain.money(get('total'))}, due {get('due_date')}."
