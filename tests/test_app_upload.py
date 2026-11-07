# tests/test_app_upload.py — judge CSV upload: strict loader errors are 400s with reasons; data never reaches the DB.
import os
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import config, state
    from app.main import app
except ImportError:  # fastapi not installed in this interpreter
    app = None


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class UploadTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.c = TestClient(app)
        self.bank, self.ledger = config.BANK_CSV.read_bytes(), config.LEDGER_CSV.read_bytes()

    def up(self, bank, ledger):
        return self.c.post("/upload", files={"bank": ("b.csv", bank), "ledger": ("l.csv", ledger)}, follow_redirects=False)

    def test_good_upload_runs_matcher_only_and_is_unlisted(self):
        r = self.up(self.bank, self.ledger)
        self.assertEqual(r.status_code, 303)
        run = state.RUNS[r.headers["location"].rsplit("/", 1)[-1]]
        self.assertTrue(run.uploaded)
        self.assertIn("model is off for uploads", run.source)
        self.assertTrue(all(p.proposer != "model stand-in (offline bait)" for p in run.proposals))
        page = self.c.get(r.headers["location"]).text
        self.assertIn("UPLOADED DATA", page)
        self.assertNotIn(run.id, self.c.get("/").text)

    def test_bad_files_are_clear_400s(self):
        cases = [(b"txn_id,date\nB1,2026-10-01\n", self.ledger, "missing columns"),
                 (self.bank, b"", "empty file"),
                 (bytes([0xFF, 0xFE, 0]) + b"garbage", self.ledger, "not UTF-8"),
                 (b"x" * (2 * 1024 * 1024 + 5), self.ledger, "exceeds 2 MB"),
                 (self.bank.replace(b",DR,", b",XX,", 1), self.ledger, "direction must be DR or CR")]
        for bank, ledger, msg in cases:
            r = self.up(bank, ledger)
            self.assertEqual(r.status_code, 400, msg)
            self.assertIn(msg, r.text)

    def test_missing_file_is_400(self):
        r = self.c.post("/upload", files={"bank": ("b.csv", self.bank)})
        self.assertEqual(r.status_code, 400)

    def test_uploaded_run_never_uses_writer_db(self):
        r = self.up(self.bank, self.ledger)
        rid = r.headers["location"].rsplit("/", 1)[-1]
        self.c.post(f"/runs/{rid}/approve", data={"txn_id": "*", "approver": "Maria", "role": "controller"})
        with mock.patch.dict(os.environ, {"CG_WRITER_DSN": "host=nowhere"}), \
                mock.patch("writer.db.post_entries", side_effect=AssertionError("must not touch the DB")):
            self.c.post(f"/runs/{rid}/post")
        self.assertIn("uploaded data is never written", state.RUNS[rid].store)


if __name__ == "__main__":
    unittest.main()
