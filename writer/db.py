# writer/db.py — posts approved journal entries to Postgres as cg_writer; refuses (whole batch) anything not SoD-approved.
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from core.chain import canonical
from core.sod import check_approval, check_post

SCHEMA = Path(__file__).with_name("schema.sql")
COLS = ("run_id", "txn_id", "invoice_id", "amount", "debit_gl", "credit_gl", "narrative", "approved_by", "approved_at")


class PostRefused(Exception):
    """Raised before any write when an entry lacks a valid human approval; nothing is posted."""


def row_hash(row: dict) -> str:
    """sha256 of the canonical row. Shared with verify.py so both paths hash identically."""
    r = {k: row[k] for k in COLS}
    r["amount"] = str(r["amount"])
    r["approved_at"] = r["approved_at"].astimezone(timezone.utc).isoformat()
    return hashlib.sha256(canonical(r).encode("utf-8")).hexdigest()


def apply_schema(admin_dsn: str, writer_pw: str, reader_pw: str) -> None:
    """Run schema.sql as an admin, then enable login for both roles with passwords passed in (never stored in SQL files)."""
    with psycopg.connect(admin_dsn, autocommit=True) as c:
        c.execute(SCHEMA.read_text(encoding="utf-8"))
        for role, pw in (("cg_writer", writer_pw), ("cg_reader", reader_pw)):
            c.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(pw)))


def _authorise(entry, proposal, approvals) -> None:
    d = check_post(proposal, approvals)
    if d.result != "allow":
        raise PostRefused(f"{entry.txn_id}: {d.rule}: {d.detail}")
    valid = {a.approver for a in approvals if a.txn_id == proposal.txn_id and a.decision == "approve"
             and check_approval(proposal, a).result == "allow"}
    if entry.approver not in valid:
        raise PostRefused(f"{entry.txn_id}: entry approver {entry.approver!r} is not a valid approver")
    if entry.txn_id != proposal.txn_id or proposal.parts.get(entry.inv_id) != entry.amount:
        raise PostRefused(f"{entry.txn_id}: entry does not match its approved proposal")


def post_entries(run_id: str, approved_entries, dsn: str | None = None) -> dict:
    """approved_entries: iterable of (JournalEntry, Proposal, [Approval]). All-or-nothing in one transaction."""
    items = list(approved_entries)
    for entry, proposal, approvals in items:
        _authorise(entry, proposal, approvals)  # every check before the first byte is written
    now = datetime.now(timezone.utc)
    rows = [{"run_id": run_id, "txn_id": e.txn_id, "invoice_id": e.inv_id, "amount": e.amount,
             "debit_gl": e.debit_gl, "credit_gl": e.credit_gl, "narrative": e.description,
             "approved_by": e.approver, "approved_at": now} for e, _, _ in items]
    for r in rows:
        r["row_hash"] = row_hash(r)
    insert = sql.SQL("INSERT INTO journal_entries ({}) VALUES ({})").format(
        sql.SQL(", ").join(map(sql.Identifier, COLS + ("row_hash",))),
        sql.SQL(", ").join(sql.Placeholder(k) for k in COLS + ("row_hash",)))
    with psycopg.connect(dsn or os.environ["CG_WRITER_DSN"]) as c:  # commits on clean exit, rolls back on error
        c.execute("INSERT INTO runs (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (run_id,))
        with c.cursor() as cur:
            cur.executemany(insert, rows)
    return {"written": len(rows), "hashes": [r["row_hash"] for r in rows]}
