# tests/test_bank_lock.py — a "bank details changed" reply locks the supplier: approval refused until Maria's PIN-checked call-back.
import os
import time
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
    from app.services import app_bank, approvals, bank_lock, runs
except ImportError:  # fastapi not installed in this interpreter
    app = None

SCAM = "Please note our bank details have changed. From now on pay to account 4471 2209 at First Island Bank."


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class BankLockTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        self.c = TestClient(app)
        self.c.post("/stage/clear")

    def scan(self, k):
        jid = self.c.post("/stage/scan", data={"sample": k}).json()["job"]
        for _ in range(300):
            if self.c.get(f"/stage/job/{jid}").json()["done"]:
                return
            time.sleep(0.02)

    def scam_reply(self):
        o = self.c.get("/mail/state").json()["offer"]
        self.c.post("/mail/offer", data={"keys": ",".join(o["keys"]), "text": "yes"})
        t = next(t for t in self.c.get("/mail/state").json()["threads"] if t["supplier"] == "Acme Supplies")
        self.c.post(f"/mail/{t['id']}/send", data={"body": "Hello, please correct it.\nAna"})
        self.assertEqual(self.c.post(f"/mail/{t['id']}/reply", data={"text": SCAM}).json()["status"], "flagged")
        return t["supplier"]

    def test_scam_reply_locks_supplier_until_call_back(self):
        for k in ("R01", "R07", "R03", "R04"):  # two good Acme bills, one Cobalt, then the Acme bill on hold
            self.scan(k)
        rid = app_bank.LAST_RUN["id"]
        self.assertEqual(self.scam_reply(), "Acme Supplies")
        self.assertTrue(bank_lock.locked("acme  supplies"))  # name match ignores case and spacing
        self.assertEqual([e["kind"] for e in state.CHAIN[-2:]], ["supplier_locked", "email_reply"])  # locked before the reply shows
        page = self.c.get(f"/simple/pay/{rid}").text
        self.assertIn("Acme Supplies is locked", page)
        self.assertIn("Approve 1 as Maria", page)  # only Cobalt can be approved
        self.c.post(f"/simple/pay/{rid}/approve", data={"pin": "2468"})
        run = runs.get_run(rid)
        self.assertEqual([run.ledger[p.inv_ids[0]].vendor for p in run.proposals if p.txn_id in {a.txn_id for a in run.approvals}], ["Cobalt Software"])
        self.assertTrue(any(d.rule == bank_lock.RULE for _, _, _, d in run.attempts))  # the refusal is recorded, not hidden
        # the call-back needs the tick and Maria's PIN
        self.assertIn("Tick the box", self.c.post(f"/simple/pay/{rid}/callback", data={"supplier": "Acme Supplies", "pin": "2468"}).text)
        self.assertIn("Wrong PIN", self.c.post(f"/simple/pay/{rid}/callback", data={"supplier": "Acme Supplies", "called": "yes", "pin": "0000"}).text)
        self.assertTrue(bank_lock.locked("Acme Supplies"))
        page = self.c.post(f"/simple/pay/{rid}/callback", data={"supplier": "Acme Supplies", "called": "yes", "pin": "2468"}).text
        self.assertIn("Call-back recorded", page)
        self.assertFalse(bank_lock.locked("Acme Supplies"))
        self.assertEqual(state.CHAIN[-1]["payload"]["by"], "Maria")
        self.assertIn("Approve 2 as Maria", page)
        self.c.post(f"/simple/pay/{rid}/approve", data={"pin": "2468"})
        self.assertEqual(len(runs.get_run(rid).approvals), 3)

    def test_lock_after_approval_blocks_recording(self):
        for k in ("R01", "R04"):
            self.scan(k)
        rid = app_bank.LAST_RUN["id"]
        self.c.post(f"/simple/pay/{rid}/approve", data={"pin": "2468"})
        self.assertEqual(len(runs.get_run(rid).approvals), 1)
        self.scam_reply()
        self.assertIn("Nothing approved yet", self.c.post(f"/simple/pay/{rid}/post").text)  # locked: not recorded as paid
        self.assertEqual(runs.get_run(rid).posted, set())

    def test_record_twice_in_one_run_after_call_back(self):
        for k in ("R01", "R07", "R03", "R04"):
            self.scan(k)
        rid = app_bank.LAST_RUN["id"]
        self.c.post(f"/simple/pay/{rid}/approve", data={"pin": "2468"})  # all three approved
        self.scam_reply()  # then Acme asks to change bank details
        page = self.c.get(f"/simple/pay/{rid}").text
        self.assertIn("Record 1 as paid", page)  # only Cobalt is offered; the locked Acme approvals are not
        self.c.post(f"/simple/pay/{rid}/post")
        run = runs.get_run(rid)
        self.assertEqual((len(run.posted), run.verify["match"]), (1, True))
        self.c.post(f"/simple/pay/{rid}/callback", data={"supplier": "Acme Supplies", "called": "yes", "pin": "2468"})
        self.assertIn("Record 2 as paid", self.c.get(f"/simple/pay/{rid}").text)
        self.c.post(f"/simple/pay/{rid}/post")
        run = runs.get_run(rid)
        self.assertEqual((len(run.posted), run.receipt["written"], run.verify["match"]), (3, 3, True))  # second write verified with the first

    def test_ai_refusal_names_the_approver_rule(self):
        for k in ("R01", "R03", "R04"):
            self.scan(k)
        rid = app_bank.LAST_RUN["id"]
        self.scam_reply()
        page = self.c.post(f"/simple/pay/{rid}/ai-approve").text  # it tries Cobalt (unlocked), not the locked Acme line
        self.assertIn("Refused. The AI asked to approve its own work", page)

    def test_clear_lifts_locks(self):
        bank_lock.lock("Acme Supplies", "t1")
        self.c.post("/stage/clear")
        self.assertFalse(bank_lock.locked("Acme Supplies"))


if __name__ == "__main__":
    unittest.main()
