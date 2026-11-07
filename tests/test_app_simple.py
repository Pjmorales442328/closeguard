# tests/test_app_simple.py — phone view: demo bills, per-field pick, match, AI approval refused, approve, post, QuickBooks.
import os
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
    from app.services import intake
except ImportError:  # fastapi not installed in this interpreter
    app = None


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class SimpleFlowTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        intake.reset_demo()
        self.c = TestClient(app)

    def test_whole_flow(self):
        page = self.c.get("/simple").text
        self.assertIn("On hold", page)
        self.assertIn("Which is right?", page)  # B13: the readers disagree
        b = intake.demo()
        c = next(c for c in b.cards if c.status == "confirm")
        picks = {f"pick_{f}": "0" if f == "invoice_no" else "1" for f in c.diffs}  # truth: reader A's number, B's date
        self.c.post(f"/simple/demo/{c.n}/pick", data=picks)
        self.assertEqual(c.status, "confirmed")
        r = self.c.post("/simple/demo/match", follow_redirects=False)
        rid = r.headers["location"].rsplit("/", 1)[-1]
        run = state.RUNS[rid]
        page = self.c.get(f"/simple/pay/{rid}").text
        self.assertIn("8 match the bank", page)
        self.assertIn("4 on hold", page)
        self.assertIn("Refused. The AI asked to approve its own work", self.c.post(f"/simple/pay/{rid}/ai-approve").text)
        self.assertEqual(run.approvals, [])
        self.assertIn("Nothing approved yet", self.c.post(f"/simple/pay/{rid}/post").text)
        self.assertIn("Wrong PIN", self.c.post(f"/simple/pay/{rid}/approve", data={"ack": "yes", "pin": "0000"}).text)
        self.assertEqual(run.approvals, [])  # a wrong PIN approves nothing
        self.c.post(f"/simple/pay/{rid}/approve", data={"ack": "yes", "pin": "2468"})
        self.assertEqual(len(run.approvals), 8)
        page = self.c.post(f"/simple/pay/{rid}/post").text
        self.assertRegex(page, r"\d+ payments recorded as paid")
        self.assertIn("Double-checked", page)
        self.assertIn(f"/simple/pay/{rid}/export", page)
        self.assertNotIn("text/csv", self.c.post(f"/simple/pay/{rid}/export", data={"pin": "1111"}).headers["content-type"])  # wrong PIN: no file
        r = self.c.post(f"/simple/pay/{rid}/export", data={"pin": "2468"})
        self.assertTrue(r.headers["content-type"].startswith("text/csv"))
        self.assertEqual(state.CHAIN[-1]["kind"], "books_exported")


if __name__ == "__main__":
    unittest.main()
