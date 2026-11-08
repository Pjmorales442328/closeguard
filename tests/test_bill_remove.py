# tests/test_bill_remove.py — Ana removes one bill: gone from every screen, chained in the audit trail, refused once Maria approved.
import os
import time
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
    from app.services import app_bank, signin, stage_job
except ImportError:  # fastapi not installed in this interpreter
    app = None


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class RemoveBillTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        self.c = TestClient(app)
        self.c.post("/stage/clear")
        signin._fails.clear()
        for k in ("R01", "R03", "R04"):
            jid = self.c.post("/stage/scan", data={"sample": k}).json()["job"]
            for _ in range(300):
                if self.c.get(f"/stage/job/{jid}").json()["done"]:
                    break
                time.sleep(0.02)

    def bills(self):
        return self.c.get("/app/state").json()["bills"]

    def test_remove_one_bill_everywhere_and_chained(self):
        b = next(x for x in self.bills() if x["invoice_no"].startswith("COB"))
        n = len(state.CHAIN)
        self.assertEqual(self.c.post("/app/bill/remove", data={"bill": b["id"]}).json(), {"ok": True})
        s = self.c.get("/app/state").json()
        self.assertNotIn(b["id"], [x["id"] for x in s["bills"]])
        self.assertEqual(len(stage_job.SCANNED), 2)
        self.assertEqual([e["payload"]["invoice_no"] for e in state.CHAIN[n:] if e["kind"] == "bill_removed"], [b["invoice_no"]])
        self.assertIn("Removed the Cobalt Software bill", s["activity"][0]["text"])
        self.assertFalse(any(x["kind"] == "pay" and "COB" in x["text"] for x in s["bank"]["lines"]))  # no longer matched to its payment
        r = self.c.post("/app/bill/remove", data={"bill": b["id"]})
        self.assertEqual((r.status_code, r.json()["error"]), (409, "That bill is already gone."))
        self.assertEqual(self.c.post("/app/bill/remove", data={"bill": "junk"}).status_code, 409)

    def test_refused_after_maria_approved(self):
        self.c.post(f"/simple/pay/{app_bank.LAST_RUN['id']}/approve", data={"pin": "2468"})
        b = self.bills()[0]
        r = self.c.post("/app/bill/remove", data={"bill": b["id"]})
        self.assertEqual(r.status_code, 409)
        self.assertIn("already approved", r.json()["error"])
        self.assertIn(b["id"], [x["id"] for x in self.bills()])


if __name__ == "__main__":
    unittest.main()
