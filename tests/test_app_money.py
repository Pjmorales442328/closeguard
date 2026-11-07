# tests/test_app_money.py — the owner's view: money stopped (from real bill and bank lines), due/late per bill, plain activity list.
import os
import time
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app.main import app
except ImportError:  # fastapi not installed in this interpreter
    app = None


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class MoneyTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {"CG_TODAY": "2026-11-07"})
        p.start()
        self.addCleanup(p.stop)
        self.c = TestClient(app)
        self.c.post("/stage/clear")

    def scan(self, k):
        jid = self.c.post("/stage/scan", data={"sample": k}).json()["job"]
        for _ in range(200):
            if self.c.get(f"/stage/job/{jid}").json()["done"]:
                return
            time.sleep(0.02)

    def test_stopped_due_and_activity(self):
        for k in ("R01", "R02", "R04", "R05", "R06", "R09"):
            self.scan(k)
        d = self.c.get("/app/state").json()
        got = {(x["who"], x["amount"]) for x in d["stopped"]["items"]}
        self.assertEqual(got, {("Birch Logistics", "2,979.29"), ("Falcon Freight", "200.00"),  # paid twice; only the $200 difference
                               ("Nightfall Consulting", "453.06"), ("Acme Supplies", "1,519.73")})  # unapproved supplier; held bill
        self.assertEqual(d["stopped"]["total"], "5,152.08")
        by = {b["supplier"] + b["invoice_no"]: d["due"]["bills"][b["id"]]["text"] for b in d["bills"]}
        self.assertEqual(by["Acme SuppliesACM-46048"], "Paid Oct 7")
        self.assertEqual(by["Acme SuppliesACM-89840"], "on hold, 5 days late")  # due Nov 2, never paid
        self.assertEqual(d["due"]["late"][0], 1)
        rid = self.c.post("/stage/run").json()["run"]
        self.c.post(f"/simple/pay/{rid}/ai-approve")
        self.c.post(f"/simple/pay/{rid}/approve", data={"ack": "yes", "pin": "2468"})
        acts = [a["who"] + ": " + a["text"] for a in self.c.get("/app/state").json()["activity"]]
        self.assertTrue(acts[0].startswith("Maria: Approved 2 payments"), acts[:3])
        self.assertIn("AI: Asked to approve a payment itself. Refused by the rules: only a named person can approve", acts)
        page = self.c.get("/app/report").text
        for want in ("October, in one page", "$5,152.08", "Acme Supplies</b> $1,519.73 is past its due date", "Refused by the rules"):
            self.assertIn(want, page)


if __name__ == "__main__":
    unittest.main()
