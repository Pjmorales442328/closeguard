# app/services/posting.py — post approved entries via writer.db (Postgres) or a labelled in-memory demo store; then verify.
import threading
from datetime import datetime, timezone

from app import config, state
from app.services.approvals import locked_vendor
from core.models import JournalEntry
from writer import db

AP_GL, BANK_GL = "2000", "1010"  # Dr Accounts Payable, Cr Bank: paying an approved invoice
DEMO_ROWS: list = []  # the "demo store" used when no CG_WRITER_DSN is configured
_POSTING = threading.Lock()  # one write at a time: a double click must not record a line twice


def store_name() -> str:
    return "postgres" if config.writer_dsn() else "demo store (in-memory, no database configured)"


def _items(run: state.Run) -> list:
    by_txn = {a.txn_id: a for a in run.approvals}
    items = []
    for p in run.proposals:
        a = by_txn.get(p.txn_id)
        if not a or p.txn_id in run.posted or locked_vendor(run, p):
            continue  # a supplier locked after approval stays unpaid until the call-back
        for inv, amt in p.parts.items():
            desc = f"Pay {inv} {run.ledger[inv].vendor} from bank {p.txn_id} ({'UPLOADED' if run.uploaded else 'SYNTHETIC'})"
            items.append((JournalEntry(p.txn_id, inv, amt, AP_GL, BANK_GL, desc, a.approver), p, run.approvals))
    return items


def _demo_post(run_id: str, items) -> dict:
    for e, p, approvals in items:
        db._authorise(e, p, approvals)  # same SoD/amount checks as the real writer, before any write
    now = datetime.now(timezone.utc)
    rows = [{"run_id": run_id, "txn_id": e.txn_id, "invoice_id": e.inv_id, "amount": e.amount, "debit_gl": e.debit_gl,
             "credit_gl": e.credit_gl, "narrative": e.description, "approved_by": e.approver, "approved_at": now}
            for e, _, _ in items]
    for r in rows:
        r["row_hash"] = db.row_hash(r)
    DEMO_ROWS.extend(rows)
    return {"written": len(rows), "hashes": [r["row_hash"] for r in rows]}


def _demo_verify(run_id: str, receipt: dict) -> dict:
    rows = [r for r in DEMO_ROWS if r["run_id"] == run_id]
    rec = [db.row_hash(r) for r in rows]
    ok = all(h == r["row_hash"] for h, r in zip(rec, rows)) and sorted(rec) == sorted(receipt["hashes"])
    return {"reader_count": len(rows), "writer_count": receipt["written"], "match": ok and len(rows) == receipt["written"]}


def post(run: state.Run) -> dict:
    """All-or-nothing. Raises db.PostRefused if nothing is approved or any entry fails authorisation."""
    with _POSTING:
        return _post(run)


def _post(run: state.Run) -> dict:
    items = _items(run)
    if not items:
        raise db.PostRefused("policy.unapproved_post: nothing approved and unposted")
    real = config.writer_dsn() and not run.uploaded  # uploaded data is never written to the database
    new = db.post_entries(run.id, items, config.writer_dsn()) if real else _demo_post(run.id, items)
    old = run.receipt or {"written": 0, "hashes": []}  # an earlier write in this run (a supplier unlocked later)
    receipt = {**new, "written": old["written"] + new["written"], "hashes": old["hashes"] + new["hashes"]}
    if real:
        from writer.verify import verify_run
        check = verify_run(run.id, receipt, config.reader_dsn())  # second path: read-only role
    else:
        check = _demo_verify(run.id, receipt)
    with state.LOCK:
        run.posted |= {e.txn_id for e, _, _ in items}
        for (e, _, _), h in zip(items, new["hashes"]):  # writer returns hashes in item order
            run.row_hashes.setdefault(e.txn_id, []).append(h)
        run.receipt, run.verify = receipt, check
        run.store = "demo store (in-memory; uploaded data is never written to the database)" if run.uploaded else store_name()
        state.log("post", {"run_id": run.id, "store": run.store, "written": new["written"], "hashes": new["hashes"],
                           "run_total": receipt["written"]})
        state.log("verify_db", {"run_id": run.id, **check})
    return {"receipt": receipt, "verify": check, "store": run.store}
