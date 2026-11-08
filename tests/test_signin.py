# tests/test_signin.py — Maria's PIN remembered for an hour: signed cookie, empty PIN never counts as wrong, forged cookie refused, Forget works.
import os
import time
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
    from app.services import app_bank, runs, signin
except ImportError:  # fastapi not installed in this interpreter
    app = None


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class RememberPinTest(unittest.TestCase):
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
        self.rid = app_bank.LAST_RUN["id"]

    def test_empty_pin_is_not_a_wrong_try(self):
        n = len(state.CHAIN)
        self.assertIn("Enter Maria", self.c.post(f"/simple/pay/{self.rid}/approve", data={"pin": ""}).text)
        self.assertEqual(runs.get_run(self.rid).approvals, [])
        self.assertFalse(any(e["kind"] == "pin_refused" for e in state.CHAIN[n:]))

    def test_remember_then_no_pin_for_the_next_steps(self):
        r = self.c.post(f"/simple/pay/{self.rid}/approve", data={"pin": "2468", "remember": "yes"})
        self.assertIn("remembered on this browser", r.text)
        self.assertEqual(len(runs.get_run(self.rid).approvals), 2)
        self.assertEqual(state.CHAIN[-1]["kind"], "pin_remembered")
        self.c.post(f"/simple/pay/{self.rid}/post")
        d = self.c.post(f"/simple/pay/{self.rid}/export", data={"pin": ""})  # no PIN typed: the remembered browser is enough
        self.assertIn("text/csv", d.headers["content-type"])
        self.c.post("/signin/forget")
        self.assertIn("Enter Maria", self.c.post(f"/simple/pay/{self.rid}/export", data={"pin": ""}).text)

    def test_without_remember_no_cookie(self):
        self.c.post(f"/simple/pay/{self.rid}/approve", data={"pin": "2468"})
        self.assertNotIn(signin.COOKIE, self.c.cookies)

    def test_forged_or_expired_cookie_is_refused(self):
        until = int(time.time()) + 600
        self.c.cookies.set(signin.COOKIE, f"Maria|{until}|{'0' * 64}")
        self.assertIn("Enter Maria", self.c.post(f"/simple/pay/{self.rid}/approve", data={"pin": ""}).text)
        self.c.cookies.set(signin.COOKIE, f"Maria|{until - 1200}|{signin._sig('Maria', until - 1200)}")
        self.assertIn("Enter Maria", self.c.post(f"/simple/pay/{self.rid}/approve", data={"pin": ""}).text)
        self.assertEqual(runs.get_run(self.rid).approvals, [])

    def test_bad_cookie_does_not_break_pages(self):
        fake = mock.Mock(cookies={signin.COOKIE: "Maria|9999999999|é"})  # non-ASCII signature: compare_digest raises TypeError
        self.assertEqual(signin.remembered(fake, "Maria"), 0)
        self.c.cookies.set(signin.COOKIE, "junk")
        self.assertEqual(self.c.get(f"/simple/pay/{self.rid}").status_code, 200)

    def test_wrong_pin_lock_covers_remembered_browser_and_forget_is_chained(self):
        self.c.post(f"/simple/pay/{self.rid}/approve", data={"pin": "2468", "remember": "yes"})
        self.c.post(f"/simple/pay/{self.rid}/post")
        for _ in range(5):
            self.c.post(f"/simple/pay/{self.rid}/export", data={"pin": "0000"})
        r = self.c.post(f"/simple/pay/{self.rid}/export", data={"pin": ""})
        self.assertIn("Too many wrong PINs", r.text)  # remembered, but locked: no file
        self.c.post("/signin/forget", headers={"referer": f"http://testserver/simple/pay/{self.rid}"})
        self.assertEqual(state.CHAIN[-1]["kind"], "pin_forgotten")


if __name__ == "__main__":
    unittest.main()
