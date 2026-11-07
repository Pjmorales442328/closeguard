# tests/test_app_stage.py — 3D scan room backend: sample scan JSON, real chain lines in the log, close run from scanned bills.
import os
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
    from app.services import stage_job
except ImportError:  # fastapi not installed in this interpreter
    app = None


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class StageTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        stage_job.clear()
        self.c = TestClient(app)

    def scan(self, k):
        import time
        jid = self.c.post("/stage/scan", data={"sample": k}).json()["job"]
        for _ in range(200):
            j = self.c.get(f"/stage/job/{jid}").json()
            if j["done"]:
                self.steps = j["steps"]
                return j["v"]
            time.sleep(0.02)
        self.fail("scan never finished")

    def test_scan_log_run(self):
        self.assertEqual(self.c.get("/stage").status_code, 200)
        after = len(state.CHAIN)
        v = self.scan("B07")
        self.assertEqual(v["status"], "refused")
        self.assertFalse(next(s for s in v["stamps"] if not s["ok"])["ok"])
        keys = [s["key"] for s in self.steps]
        self.assertEqual(keys[:3], ["vm", "send0", "send1"])
        self.assertEqual(sorted(k for k in keys if k.startswith("read")), ["read0", "read1"])
        self.assertIn("The line items add up to", " ".join(s["text"] for s in self.steps if not s["ok"]))
        self.assertEqual(keys[-1], "chain")
        ok = self.scan("B02")
        self.assertEqual((ok["status"], ok["scanned"]), ("ready", 2))
        lines = self.c.get(f"/stage/log?after={after}").json()["lines"]
        self.assertTrue(any("failed intake.line_sum" in l["text"] for l in lines))
        self.assertTrue(all(l["seq"] > after for l in lines))
        r = self.c.post("/stage/run").json()
        self.assertEqual(r["allowed"], 1)  # only B02 passed; it matches one bank payment
        self.assertIn(r["run"], state.RUNS)

    def test_duplicate_caught_across_scans(self):
        self.scan("B02")
        v = self.scan("B08")
        self.assertEqual(v["status"], "refused")
        self.assertIn("duplicate invoice", [s["text"] for s in v["stamps"] if not s["ok"]])

    def test_talk_ana_answers_maria_confirms(self):
        v = self.scan("B13")
        self.assertEqual(v["status"], "confirm")
        self.assertIn("disagree on the invoice number", v["say"]["text"])
        a = self.c.post("/stage/answer", data={"bill": v["id"], "text": "banana"}).json()
        self.assertIn("Sorry", a["reply"]["text"])
        a = self.c.post("/stage/answer", data={"bill": v["id"], "text": "FAL-24371"}).json()
        self.assertIn("due date", a["reply"]["text"])
        a = self.c.post("/stage/answer", data={"bill": v["id"], "text": "November second", "heard": "November second"}).json()
        self.assertTrue(a["ready_for_maria"])
        d = self.c.post("/stage/confirm", data={"bill": v["id"]}).json()
        self.assertEqual(d["v"]["status"], "confirmed")
        self.assertTrue(any(e["kind"] == "voice_answer" and e["payload"]["heard"] for e in state.CHAIN))

    def test_app_screen_state(self):
        self.assertEqual(self.c.get("/app?embed=1").status_code, 200)
        self.scan("B02"), self.scan("B07"), self.scan("B13")
        d = self.c.get("/app/state").json()
        self.assertEqual([b["kind"] for b in d["bills"]], ["check", "hold", "pay"])  # newest first
        self.assertIn("1,569.73", d["bills"][1]["note"])
        self.assertIn("Please check the paper", d["bills"][0]["note"])
        self.assertEqual(d["summary"]["pay"], [0, "0.00", 1])  # B02 passed, and its payment is already on the bank statement
        self.assertEqual([b["label"] for b in d["bills"]], ["Needs checking", "On hold", "Ready to pay"])
        self.assertIn(["Invoice number", "FAL-24371 or FAL-24378", True], d["bills"][0]["rows"])

    def test_bank_tab_ticks_off_payments(self):
        self.c.post("/stage/clear")
        k = self.c.get("/app/state").json()["bank"]
        self.assertEqual((k["matched"], k["count"], {x["kind"] for x in k["lines"]}), (False, 12, {"wait"}))
        self.scan("B02"), self.scan("B13")
        self.assertTrue(self.c.get("/app/state").json()["bank"]["matched"])  # matched right after the scan, no button
        self.assertEqual(self.c.post("/stage/run").status_code, 200)
        by = {x["txn"]: x for x in self.c.get("/app/state").json()["bank"]["lines"]}
        self.assertEqual(by["BB002"]["kind"], "pay")
        self.assertEqual(by["BB004"]["text"], "Paid twice: this bill was already paid on Oct 9")  # the same bill paid twice
        self.assertIn("needs a person", by["BB003"]["text"])  # bill scanned but a person has not checked it
        self.assertEqual((by["BB009"]["kind"], by["BB009"]["text"]), ("wait", "Waiting for its bill: scan it to match"))
        self.c.post("/stage/clear")
        self.assertFalse(self.c.get("/app/state").json()["bank"]["matched"])

    def test_photo_receipts(self):
        self.c.post("/stage/clear")
        self.assertEqual(self.scan("R04")["status"], "refused")  # lines do not add up (committed cache of the real reads)
        self.assertEqual(self.scan("R09")["status"], "ready")  # total raised by $200: passes the scan, caught at the bank
        self.scan("R01")
        self.assertEqual(self.c.post("/stage/run").status_code, 200)
        by = {x["txn"]: x for x in self.c.get("/app/state").json()["bank"]["lines"]}
        self.assertEqual(by["BB006"]["text"], "Amount differs: the bill says $3,613.13, the bank paid $3,413.13")
        self.assertEqual(by["BB001"]["kind"], "pay")

    def test_unknown_supplier_is_on_hold_in_the_app(self):
        self.c.post("/stage/clear")
        self.scan("R06")  # Nightfall Consulting: reads fine, but is not on the approved supplier list
        d = self.c.get("/app/state").json()
        b = d["bills"][0]
        self.assertEqual((b["kind"], d["summary"]["pay"][0], d["summary"]["hold"]), ("hold", 0, 1))
        self.assertIn("not on your approved supplier list", b["note"])
        self.assertIsNone(self.c.get("/mail/state").json()["offer"])  # no "send a corrected bill" email to an unknown supplier

    def test_unknown_sample_refused(self):
        self.assertEqual(self.c.post("/stage/scan", data={"sample": "../x"}).status_code, 415)
        self.assertEqual(self.c.post("/stage/run").status_code, 400)


if __name__ == "__main__":
    unittest.main()
