# app/services/mail.py — supplier emails: Closeguard drafts from the check results, Ana approves, follow-ups go out on time, replies are read.
# DEMO OUTBOX: nothing leaves this server. Production would send through the company mailbox (SMTP/IMAP); the flow is the same.
import os
import re
import threading
import time
import uuid
from pathlib import Path

from agent import extract, mail_read
from app import config, state
from app.services import bank_lock

THREADS: dict = {}  # thread id -> thread; shared demo state, cleared with the scan room
ASKED: dict = {}  # problem key -> True (Ana said draft it) / False (not now); nothing is drafted before she says yes
_lock = threading.Lock()
SIGN = "Ana Reyes\nBookkeeper, Tidewater Catering Co."
MAX_FOLLOWUPS = 2


def followup_seconds() -> int:
    return int(os.environ.get("CG_FOLLOWUP_SECONDS") or 120)  # demo pace; a real business would use about 3 days


def address(supplier: str) -> str:
    return f"billing@{re.sub(r'[^a-z0-9]+', '-', supplier.lower()).strip('-')}.example"  # .example = reserved, can never deliver


def _draft(key, supplier, subject, why, ask):
    body = f"Hello {supplier} team,\n\n{why}\n\n{ask}\n\nThank you,\n{SIGN}"
    return {"id": uuid.uuid4().hex[:10], "key": key, "supplier": supplier, "to": address(supplier), "subject": subject, "why": why,
            "status": "draft", "msgs": [{"dir": "out", "at": time.time(), "body": body, "draft": True}], "next_at": None, "followups": 0}


def wanted(bills: list, bank: dict) -> list:
    """The emails a bookkeeper would write today, from the facts on screen (no AI writing the numbers).
    Note: payments with no bill at all get no draft yet (8 near-identical asks would bury the important ones)."""
    out, refs = [], {x["ref"] for x in bank.get("lines", []) if x.get("kind") != "wait"}
    for b in bills:
        if b["kind"] == "hold" and b["note"] and b["invoice_no"] and not b["new_supplier"] and b["invoice_no"] not in refs:  # an unknown supplier needs approval, not a corrected bill
            out.append((f"bill:{b['id']}", b["supplier"], f"Bill {b['invoice_no']}: corrected copy needed",
                        f"We received your bill {b['invoice_no']} for ${b['total']}, but we cannot pay it as it is. {b['note']}",
                        "Could you please send us a corrected bill? We will pay as soon as it arrives.",
                        f"the {b['supplier']} bill is on hold: {b['note'][:1].lower()}{b['note'][1:].rstrip('.')}"))
    for x in bank.get("lines", []) if bank.get("matched") else []:
        t, who, ref = x["text"], x["who"], x["ref"]
        if t.startswith("Paid twice"):
            out.append((f"bank:{x['txn']}", who, f"Double payment on {ref}: refund please",
                        f"Our bank statement shows we paid your bill {ref} twice: ${x['amount']} on two dates.",
                        "Could you please refund the second payment, or tell us when you will?",
                        f"{who} was paid twice for {ref}"))
        elif t.startswith("Amount differs"):
            out.append((f"bank:{x['txn']}", who, f"Bill {ref}: amount does not match our payment", t.replace("Amount differs: the bill says", f"Your bill {ref} says").replace("the bank paid", "but we paid") + ".",
                        "Could you please check which amount is right and send a corrected bill if needed?",
                        f"the {who} bill and our payment do not match"))
    return out


def sync(bills: list, bank: dict) -> None:
    """New drafts for new problems; due follow-ups go out (Ana approved them with the first email)."""
    now = time.time()
    with _lock:
        keys = {t["key"] for t in THREADS.values()}
        for w in wanted(bills, bank):
            if w[0] not in keys and ASKED.get(w[0]):
                t = _draft(*w[:5])
                THREADS[t["id"]] = t
        for t in THREADS.values():
            if t["status"] == "waiting" and t["next_at"] and now >= t["next_at"]:
                if t["followups"] >= MAX_FOLLOWUPS:
                    t["status"], t["next_at"] = "no_reply", None
                    continue
                t["followups"] += 1
                n = t["followups"]
                t["msgs"].append({"dir": "out", "at": now, "auto": True, "body": f"Hello again,\n\nJust following up on my email below about "
                                  f"\"{t['subject']}\". Could you reply when you can?\n\nThank you,\n{SIGN}"})
                t["next_at"] = now + followup_seconds()
                with state.LOCK:
                    state.log("email_followup", {"thread": t["id"], "to": t["to"], "n": n, "demo_outbox": True})


def offer(bills: list, bank: dict) -> list:
    """Problems Closeguard has not asked Ana about yet: [(key, supplier, spoken heads-up)]."""
    return [(w[0], w[1], w[5]) for w in wanted(bills, bank) if w[0] not in ASKED]


def decide(keys: list, yes: bool, bills: list, bank: dict) -> list:
    """Ana's answer to the offer; on yes the drafts exist right away. Returns the suppliers drafted for."""
    with _lock:
        for k in keys:
            ASKED[k] = yes
    sync(bills, bank)
    return [t["supplier"] for t in THREADS.values() if t["key"] in keys]


def send(tid: str, body: str, who: str = "Ana") -> dict:
    with _lock:
        t = THREADS[tid]
        if t["status"] != "draft":
            raise ValueError("already sent")
        t["msgs"][0] = {"dir": "out", "at": time.time(), "body": body.strip()[:4000], "by": who,
                        "msg_id": f"<demo-{uuid.uuid4().hex[:12]}@closeguard>"}
        t["status"], t["next_at"] = "waiting", time.time() + followup_seconds()
        with state.LOCK:
            state.log("email_sent", {"thread": t["id"], "to": t["to"], "subject": t["subject"], "approved_by": who,
                                     "msg_id": t["msgs"][0]["msg_id"], "demo_outbox": True})
        return t


def reply(tid: str, text: str) -> dict:
    """A supplier reply arrives (demo: typed on the page). Read by the model; a scam tripwire overrides it; nothing is paid or changed."""
    t = THREADS[tid]
    live = config.model_live() and extract._allow_live()
    res, meta = mail_read.analyse(text, live, Path(os.environ.get("CG_VAR_DIR", "var")) / "cache_mail")
    status = "flagged" if res["scam"] else {"corrected_bill": "done", "promise": "promised"}.get(res["intent"], "replied")
    with _lock:
        if res["scam"]:
            bank_lock.lock(t["supplier"], t["id"])  # before anything shows the reply, so no payment slips through in between
        t["msgs"].append({"dir": "in", "at": time.time(), "body": text[:4000], "read": res, "meta": meta})
        t["status"], t["next_at"] = status, None  # any reply stops the follow-ups
        with state.LOCK:
            state.log("email_reply", {"thread": t["id"], "from": t["to"], "intent": res["intent"], "scam": res["scam"],
                                      "model": meta.get("model"), "vultr": (meta.get("vultr") or {}).get("id"), "demo_outbox": True})
    return t


def clear() -> None:
    with _lock:
        THREADS.clear()
        ASKED.clear()
    bank_lock.clear()
