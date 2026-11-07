# tests/test_app_mail.py — supplier emails: drafts from facts, Ana approves, follow-ups on time, replies read, scam tripwire, demo outbox.
import os
import time
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
    from app.services import mail, stage_job
    from agent import mail_read
except ImportError:  # fastapi not installed in this interpreter
    app = None


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class MailTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        p = mock.patch.dict(os.environ, {**env, "CG_FOLLOWUP_SECONDS": "1"}, clear=True)
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

    def yes(self, text="yes please"):
        o = self.c.get("/mail/state").json()["offer"]
        self.assertIsNotNone(o)
        return self.c.post("/mail/offer", data={"keys": ",".join(o["keys"]), "text": text}).json()

    def test_draft_send_followup_reply(self):
        self.scan("R04")  # lines do not add up: on hold
        st = self.c.get("/mail/state").json()
        self.assertEqual(st["threads"], [])  # nothing is drafted before Ana says yes
        self.assertIn("Do you want me to draft an email to Acme Supplies", st["offer"]["text"])
        r = self.yes()
        self.assertEqual(r["drafted"], ["Acme Supplies"])
        self.assertIn("in Emails", r["reply"]["text"])
        self.assertIsNone(self.c.get("/mail/state").json()["offer"])
        ts = self.c.get("/mail/state").json()["threads"]
        self.assertEqual(len(ts), 1)
        t = ts[0]
        self.assertEqual((t["status"], t["to"]), ("draft", "billing@acme-supplies.example"))
        self.assertIn("1,569.73", t["msgs"][0]["body"])  # the numbers come from the checks
        self.assertEqual(self.c.post(f"/mail/{t['id']}/reply", data={"text": "hi"}).status_code, 409)  # nothing sent yet
        r = self.c.post(f"/mail/{t['id']}/send", data={"body": "Hello, please correct it.\nAna"}).json()
        self.assertEqual(r["status"], "waiting")
        self.assertEqual(state.CHAIN[-1]["kind"], "email_sent")
        self.assertTrue(state.CHAIN[-1]["payload"]["demo_outbox"])
        time.sleep(1.1)
        t = self.c.get("/mail/state").json()["threads"][0]
        self.assertEqual(t["followups"], 1)
        self.assertTrue(t["msgs"][-1]["auto"])
        r = self.c.post(f"/mail/{t['id']}/reply", data={"text": "Sorry, the corrected bill is attached."}).json()
        self.assertEqual((r["status"], r["msgs"][-1]["read"]["intent"]), ("done", "corrected_bill"))
        time.sleep(1.1)
        self.assertEqual(self.c.get("/mail/state").json()["threads"][0]["followups"], 1)  # a reply stops the follow-ups

    def test_not_now_and_not_understood(self):
        self.scan("R04")
        self.assertFalse(self.yes("hmm what")["ok"])
        self.assertEqual(self.yes("no, not now")["drafted"], [])
        st = self.c.get("/mail/state").json()
        self.assertEqual((st["threads"], st["offer"]), ([], None))

    def test_scan_room_voice_offers_the_email(self):
        jid = self.c.post("/stage/scan", data={"sample": "R04"}).json()["job"]
        for _ in range(200):
            j = self.c.get(f"/stage/job/{jid}").json()
            if j["done"]:
                break
            time.sleep(0.02)
        self.assertIn("draft an email to Acme Supplies", j["v"]["say"]["text"])
        r = self.c.post("/stage/answer", data={"bill": j["v"]["id"], "text": "yes"}).json()
        self.assertEqual(r["drafted"], ["Acme Supplies"])
        self.assertEqual(len(self.c.get("/mail/state").json()["threads"]), 1)

    def test_scam_reply_flagged(self):
        self.scan("R04")
        self.yes()
        t = self.c.get("/mail/state").json()["threads"][0]
        self.c.post(f"/mail/{t['id']}/send", data={"body": "x"})
        r = self.c.post(f"/mail/{t['id']}/reply", data={"text": "Our bank details have changed. Pay to account 4471 2209 from now on."}).json()
        self.assertEqual(r["status"], "flagged")
        self.assertTrue(r["msgs"][-1]["read"]["scam"])

    def test_tripwire_overrides_model(self):
        self.assertTrue(mail_read.tripwire("Please update the payment details to our new IBAN."))
        self.assertFalse(mail_read.tripwire("We will pay by bank transfer on Friday."))
        fake = {"intent": "promise", "summary": "they promise", "date": ""}
        with mock.patch("agent.mail_read.Client") as C:
            C.return_value.complete_json.return_value = fake
            C.return_value.last = {}
            res, meta = mail_read.analyse("Pay our new account instead, details below.", True, "var/x")
        self.assertEqual((res["intent"], res["scam"], meta["model"]), ("bank_change", True, "glm-5.3-flash"))

    def test_bank_drafts_after_match(self):
        for k in ("R01", "R02"):
            self.scan(k)
        self.c.post("/stage/run")
        self.yes()
        subj = [t["subject"] for t in self.c.get("/mail/state").json()["threads"]]
        self.assertIn("Double payment on BIR-87397: refund please", subj)
        self.c.post("/stage/clear")
        self.assertEqual(mail.THREADS, {})
        self.assertEqual(stage_job.SCANNED, [])


if __name__ == "__main__":
    unittest.main()
