# app/services/stage_job.py — one scan as a background job whose real steps (upload, each Vultr reader, checks, chain) are timed.
import threading
import time
import uuid

from agent.extract import MODELS
from app import config, state
from app.services import desk, intake, intake_read as ir, plain, stage_voice

SCANNED: list = []  # (batch_id, n) scanned in the scan room, oldest first; shared demo state, cleared by Clear
JOBS: dict = {}
LATEST: dict = {"job": None}  # newest scan job, for the app screen
_lock = threading.Lock()
CHECK = {"line_sum": "lines add up to the total", "dates": "dates make sense", "duplicate_invoice": "invoice number not seen before",
         "amount_positive": "amount is positive", "currency": "currency is USD", "vendor_known": "supplier is on the list"}


def _earlier_refs() -> frozenset:
    """Invoice numbers of the bills scanned before, so the duplicate check works across scans."""
    out = set()
    for bid, n in list(SCANNED):
        b = intake.get(bid)
        c = next((c for c in b.cards if c.n == n), None) if b else None
        r = c and (ir.final(c) if c.status in ("ready", "confirmed") else next((r for r in c.readings if r), None))
        if r:
            out.add(ir.ref_key(r.invoice_no))
    return frozenset(out)


def _run(job: dict, name: str, data: bytes) -> None:
    t0 = time.monotonic()
    step = lambda key, text, ok=True, **kw: job["steps"].append({"key": key, "ms": round((time.monotonic() - t0) * 1000), "text": text, "ok": ok, **kw})  # noqa: E731
    try:
        b = intake.receive([(name, data)])
        c = b.cards[0]
        step("vm", f"Received on the Vultr server: {len(data):,} bytes, fingerprint {c.sha[:12]}")
        live = config.model_live()
        for i, m in enumerate(MODELS):
            step(f"send{i}", f"Sent to {plain.READERS[i]} ({m}) on Vultr Serverless Inference" + ("" if live else " (offline: saved answer)"))

        def on_read(i, raw, meta):
            u = meta.get("usage") or {}
            how = "saved answer" if meta.get("cached") else "live answer"
            text = (f"{plain.READERS[i]} answered in {meta.get('latency_s') or 0:.2f} s ({how}, {(u.get('prompt') or 0) + (u.get('completion') or 0):,} tokens)"
                    if raw is not None else f"{plain.READERS[i]} could not read it: {meta.get('error', 'no answer')}")
            fields = {k: str(raw.get(k)) for k in ("supplier", "invoice_no", "total", "due_date")} if isinstance(raw, dict) else {}
            step(f"read{i}", text, raw is not None, fields=fields, vultr=meta.get("vultr"))

        ir.read_card(c, _earlier_refs(), live=live, on_read=on_read)
        step("compare", "Both readers agree on every field" if not c.diffs else f"Readers disagree on: {', '.join(plain.field(f) for f in c.diffs)}", not c.diffs)
        i = next(iter(c.checks), None)
        for key, d in zip(CHECK, c.checks.get(i) or []):
            bad = d.result == "refuse" or bool(d.flag)
            step("check", (plain.reason(d.rule, d.detail) if d.result == "refuse" else "supplier is NOT on the list: payment will be held")
                 if bad else CHECK[key], not bad)
        v = desk.view(b, c)
        with _lock:
            SCANNED.append((b.id, c.n))
        e = state.CHAIN[-1]
        step("chain", f"Written to the audit trail: entry #{e['seq']}, hash {e['hash'][:12]}")
        from app.services import app_bank  # late import (app_bank.rematch reads SCANNED)
        app_bank.rematch()  # matched with the bank statement right away; no button
        job["v"] = {**v, "image": f"/bills/{b.id}/{c.n}/image", "real": job["real"], "live": live, "scanned": len(SCANNED),
                    "say": stage_voice.prompt(v)}
    except intake.IntakeRefused as e:
        step("error", str(e), False)
    except Exception as e:  # noqa: BLE001 — the page must hear about any failure, never spin forever
        step("error", f"server error: {type(e).__name__}", False)
    job["done"] = True


def start(name: str, data: bytes, real: bool) -> str:
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "steps": [], "done": False, "v": None, "real": real}
    with _lock:
        JOBS[jid] = job
        LATEST["job"] = jid
        while len(JOBS) > 50:
            JOBS.pop(next(iter(JOBS)))
    threading.Thread(target=_run, args=(job, name, data), daemon=True).start()
    return jid


def clear() -> None:
    with _lock:
        SCANNED.clear()
