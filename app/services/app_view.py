# app/services/app_view.py — the bookkeeper app's data: scanned bills in plain business words, plus the scan in progress.
from decimal import Decimal

from app.services import intake, intake_read as ir, plain, stage_job, stage_voice

STATUS = {"ready": ("pay", "Ready to pay"), "confirmed": ("pay", "Ready to pay"), "confirm": ("check", "Needs checking"),
          "refused": ("hold", "On hold"), "unreadable": ("hold", "Can't read it, scan again"), "rejected": ("hold", "Rejected")}


def _bill(b, c) -> dict:
    r = ir.final(c) if c.status in ("ready", "confirmed") else next((x for x in c.readings if x), None)
    kind, label = STATUS.get(c.status, ("busy", "Reading…"))
    i = next(iter(c.checks), None)
    bad = [plain.reason(d.rule, d.detail) for d in c.checks.get(i) or [] if d.result == "refuse"]
    note = ""
    if c.status == "confirm":
        get = lambda k, f: str(getattr(c.readings[k], f)) if c.readings[k] else "?"  # noqa: E731
        note = "; ".join(f"the {plain.field(f)} reads {stage_voice.spoken(get(0, f))} or {stage_voice.spoken(get(1, f))}" for f in c.diffs
                         if all(c.readings)) or "only one reader could read it"
        note = "Please check the paper: " + note + "."
    elif bad:
        note = bad[0]
    elif c.status == "confirmed":
        note = f"Checked and confirmed by {c.by}."
    flag = any(d.flag for d in c.checks.get(i) or [])
    if flag and kind == "pay":  # the payment rules refuse an unknown payee, so the app never calls this bill ready to pay
        sup = (r.supplier.title() if r.supplier.isupper() else r.supplier) if r else "This supplier"
        kind, label, note = "hold", "On hold", f"New supplier: {sup} is not on your approved supplier list, so it will not be paid until someone approves the supplier."
    show = lambda f, v: stage_voice.spoken(str(v)) if f.endswith("date") else plain.money(v) if f == "total" else str(v).title() if f == "supplier" and str(v).isupper() else str(v)  # noqa: E731
    rows = []
    for f, name in (("supplier", "Supplier"), ("invoice_no", "Invoice number"), ("invoice_date", "Invoice date"),
                     ("due_date", "Due date"), ("total", "Total")):
        if c.status == "confirm" and f in c.diffs and all(c.readings):  # disputed: show both readings, never pick one silently
            rows.append([name, " or ".join(show(f, getattr(x, f)) for x in c.readings), True])
        elif r:
            rows.append([name, show(f, getattr(r, f)), False])
    return {"id": f"{b.id}/{c.n}", "image": f"/bills/{b.id}/{c.n}/image", "kind": kind, "label": label, "note": note,
            "new_supplier": flag, "supplier": (r.supplier.title() if r.supplier.isupper() else r.supplier) if r else c.name, "invoice_no": r.invoice_no if r else "",
            "date": str(r.invoice_date) if r else "", "due": str(r.due_date) if r else "",
            "total": plain.money(r.total) if r else "", "lines": [plain.money(x) for x in r.line_items] if r else [],
            "readers": [bool(x) for x in c.readings], "rows": rows}


def state() -> dict:
    bills = []
    for bid, n in reversed(list(stage_job.SCANNED)):
        b = intake.get(bid)
        c = next((c for c in b.cards if c.n == n), None) if b else None
        if c:
            bills.append(_bill(b, c))
    j = stage_job.JOBS.get(stage_job.LATEST["job"] or "")
    scanning = None
    if j and not j["done"]:
        done = {s["key"] for s in j["steps"]}
        st = lambda d, b: "done" if d in done else "busy" if b in done else "wait"  # noqa: E731
        scanning = {"step": "Reading the bill…" if "vm" in done else "Sending the photo…",
                    "readers": [st(f"read{i}", f"send{i}") for i in (0, 1)],
                    "stages": [["Photo received on the Vultr server", "done" if "vm" in done else "busy"],
                               ["Reader 1 (AI on Vultr) reads it", st("read0", "send0")], ["Reader 2 (a different AI) reads it", st("read1", "send1")],
                               ["Comparing the two readings", st("check", "compare") if "compare" in done else "wait"],
                               ["Checking the numbers with fixed rules", "busy" if "check" in done else "wait"]]}
    tot = lambda k: sum((Decimal(x["total"].replace(",", "") or 0) for x in bills if x["kind"] == k), Decimal(0))  # noqa: E731
    return {"bills": bills, "scanning": scanning,
            "summary": {"pay": [sum(x["kind"] == "pay" for x in bills), plain.money(tot("pay"))],
                        "check": sum(x["kind"] == "check" for x in bills), "hold": sum(x["kind"] == "hold" for x in bills)}}
