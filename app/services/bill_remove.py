# app/services/bill_remove.py — Ana removes one scanned bill before any payment is approved; the removal is chained, never erased.
from app import state
from app.services import app_bank, app_view, intake, mail, stage_job

REMOVED: dict = {}  # (batch, n) -> the bill as it looked, so the Activity feed can still name it


def remove(bill_id: str, who: str = "Ana (bookkeeper)") -> str | None:
    """None when removed, else the plain reason it was not. The bill leaves every screen; the audit trail keeps the removal."""
    try:
        bid, n = bill_id.rsplit("/", 1)
        key = (bid, int(n))
    except ValueError:
        return "No such bill."
    run = state.RUNS.get(app_bank.LAST_RUN["id"] or "")
    if run and (run.approvals or run.posted):  # a new match would silently drop Maria's approvals; undoing payments is another job
        return "Maria already approved or recorded payments this month, so a bill cannot be removed now."
    b = intake.get(bid)
    c = next((c for c in b.cards if c.n == key[1]), None) if b else None
    with stage_job._lock:
        if key not in stage_job.SCANNED or c is None:
            return "That bill is already gone."
        stage_job.SCANNED.remove(key)
    view = app_view._bill(b, c)
    REMOVED[key] = view
    with mail._lock:  # an email not sent yet is about a bill that is gone; sent ones stay as history
        for tid in [t for t, x in mail.THREADS.items() if x["key"] == f"bill:{bill_id}" and x["status"] == "draft"]:
            del mail.THREADS[tid]
        mail.ASKED.pop(f"bill:{bill_id}", None)
    with state.LOCK:
        state.log("bill_removed", {"bill_id": bill_id, "by": who, "supplier": view["supplier"], "invoice_no": view["invoice_no"], "total": view["total"]})
    app_bank.rematch()
    return None


def clear() -> None:
    REMOVED.clear()
