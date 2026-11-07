# app/services/app_pay.py — the pay screen of the bookkeeper app: what is paid, what is not and why (same words as the bank tab), email status.
from decimal import Decimal

from app.services import app_bank, app_view, mail, plain, runs

MAIL = {"draft": "Email drafted: Ana approves it in Emails", "waiting": "Email sent: waiting for their reply",
        "promised": "Supplier promised to fix it", "replied": "Supplier replied: Ana reads it", "done": "Supplier sent a corrected bill",
        "flagged": "Reply flagged as a possible scam", "no_reply": "No reply after 2 follow-ups: call them"}


def view(run) -> dict:
    rows = runs.rows(run)
    why = app_bank.lines_for(run, app_view.state()["bills"])
    ok, held = [], []
    for r in rows:
        b = r["b"]
        t = next((t for t in mail.THREADS.values() if b.reference in t["subject"]), None)  # the email about this bill
        x = {"who": b.counterparty, "ref": b.reference, "date": f"{b.date:%b} {b.date.day}", "amount": b.amount,
             "text": why.get(b.txn_id, {}).get("text") or plain.reason(r["d"].rule, r["d"].detail), "kind": why.get(b.txn_id, {}).get("kind", "hold"),
             "mail": t and MAIL.get(t["status"]), "mail_bad": bool(t and t["status"] in ("flagged", "no_reply")),
             "flag": r["d"].flag, "approval": r["approval"], "posted": r["posted"]}
        (ok if r["d"].result == "allow" else held).append(x)
    step = 3 if run.verify else 2 if run.approvals else 1
    return {"ok": ok, "held": held, "step": step, "flagged": sum(bool(x["flag"]) for x in ok),
            "ok_total": plain.money(sum((x["amount"] for x in ok), Decimal(0))),
            "held_total": plain.money(sum((x["amount"] for x in held), Decimal(0)))}
