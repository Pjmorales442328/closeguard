# tests/test_writer.py — writer/verify against a throwaway postgres:16 container on port 55432; skips if Docker/psycopg absent.
import secrets
import shutil
import subprocess
import time
import unittest
from decimal import Decimal

from core.models import Approval, JournalEntry, Proposal

try:
    import psycopg
    from writer.db import PostRefused, apply_schema, post_entries
    from writer.verify import verify_run
except ImportError:  # no psycopg in this interpreter -> skip, the offline core tests still run
    psycopg = None

PORT, NAME = 55432, "cg-writer-test"
PW = {k: secrets.token_urlsafe(16) for k in ("admin", "writer", "reader")}
DSN = {k: f"host=127.0.0.1 port={PORT} dbname=postgres user={u} password={PW[k]}"
       for k, u in (("admin", "postgres"), ("writer", "cg_writer"), ("reader", "cg_reader"))}


def docker_ok() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def batch(n=5, approver="Maria", role="controller"):
    out = []
    for i in range(n):
        amt = Decimal(f"{100 + i}.25")
        p = Proposal(f"B{i}", (f"I{i}",), amt, {f"I{i}": amt}, "match")
        e = JournalEntry(f"B{i}", f"I{i}", amt, "2000", "1000", f"pay I{i}", approver)
        out.append((e, p, [Approval(f"B{i}", approver, role, "approve")]))
    return out


@unittest.skipUnless(psycopg is not None and docker_ok(), "needs psycopg and a running Docker daemon")
class WriterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
        subprocess.run(["docker", "run", "--rm", "-d", "--name", NAME, "-p", f"127.0.0.1:{PORT}:5432",
                        "-e", f"POSTGRES_PASSWORD={PW['admin']}", "postgres:16"], check=True, capture_output=True)
        for _ in range(60):  # the image restarts postgres once during init; wait for the final server
            try:
                with psycopg.connect(DSN["admin"], connect_timeout=2) as c:
                    c.execute("SELECT 1")
                break
            except psycopg.OperationalError:
                time.sleep(1)
        else:
            raise RuntimeError("postgres did not start")
        time.sleep(2)
        apply_schema(DSN["admin"], PW["writer"], PW["reader"])
        apply_schema(DSN["admin"], PW["writer"], PW["reader"])  # idempotent

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker", "stop", NAME], capture_output=True)

    def post(self, run, n=5):
        return post_entries(run, batch(n), dsn=DSN["writer"])

    def test_reader_sees_writer_rows(self):
        receipt = self.post("r-ok")
        self.assertEqual(receipt["written"], 5)
        self.assertEqual(verify_run("r-ok", receipt, dsn=DSN["reader"]),
                         {"reader_count": 5, "writer_count": 5, "match": True})

    def test_update_delete_refused_for_both_roles(self):
        self.post("r-imm", 1)
        for role in ("writer", "reader"):
            for stmt in ("UPDATE journal_entries SET amount = 1 WHERE run_id = 'r-imm'",
                         "DELETE FROM journal_entries WHERE run_id = 'r-imm'", "TRUNCATE journal_entries"):
                with self.subTest(role=role, stmt=stmt), psycopg.connect(DSN[role]) as c:
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        c.execute(stmt)

    def test_reader_cannot_insert(self):
        with psycopg.connect(DSN["reader"]) as c, self.assertRaises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO runs (id) VALUES ('sneaky')")

    def test_unapproved_post_refused_and_nothing_written(self):
        bad = [batch(2)[0], batch(2, approver="agent", role="agent")[1]]
        cases = {"no approval": [(e, p, []) for e, p, _ in batch(1)],
                 "agent approver": bad,
                 "self approval": [(e, Proposal(p.txn_id, p.inv_ids, p.amount, p.parts, p.kind, proposer="Maria"), a)
                                   for e, p, a in batch(1)],
                 "amount drift": [(JournalEntry(e.txn_id, e.inv_id, e.amount + 1, e.debit_gl, e.credit_gl,
                                                e.description, e.approver), p, a) for e, p, a in batch(1)]}
        for name, items in cases.items():
            with self.subTest(name), self.assertRaises(PostRefused):
                post_entries("r-bad", items, dsn=DSN["writer"])
        with psycopg.connect(DSN["reader"]) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM journal_entries WHERE run_id='r-bad'").fetchone()[0], 0)

    def test_superuser_tamper_detected(self):
        receipt = self.post("r-tamper")
        with psycopg.connect(DSN["admin"], autocommit=True) as c:  # trigger stops even the superuser...
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                c.execute("UPDATE journal_entries SET amount = 1 WHERE run_id='r-tamper'")
        with psycopg.connect(DSN["admin"]) as c:  # ...unless it switches triggers off
            c.execute("SET session_replication_role = replica")
            c.execute("UPDATE journal_entries SET amount = amount + 0.01 WHERE run_id='r-tamper' AND txn_id='B2'")
        v = verify_run("r-tamper", receipt, dsn=DSN["reader"])
        self.assertEqual((v["reader_count"], v["match"]), (5, False))


if __name__ == "__main__":
    unittest.main()
