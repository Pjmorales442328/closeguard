# tests/test_app_desk.py — Guard Desk offline: sample bills through the real intake cache, stamps, limits, bill answers.
import os
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
    from app.services import desk, voice as sv
except ImportError:
    app = None

JPG = b"\xff\xd8\xff" + b"\0" * 50
HX = {"HX-Request": "true"}


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class DeskTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if not k.startswith("CG_")}, clear=True)
        p.start()
        self.addCleanup(p.stop)
        sv._HITS.clear()
        self.c = TestClient(app)

    def test_page_and_sample_images(self):
        self.assertIn("Guard Desk", self.c.get("/desk").text)
        self.assertEqual(self.c.get("/desk/sample/B07").status_code, 200)
        self.assertEqual(self.c.get("/desk/sample/B01").status_code, 404)

    def test_line_sum_sample_gets_a_bad_stamp(self):  # committed intake cache = no network
        r = self.c.post("/desk/scan", data={"sample": "B07"}, headers={"X-Desk": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("total does not add up", r.text)

    def test_unknown_supplier_sample(self):
        r = self.c.post("/desk/scan", data={"sample": "B09"}, headers={"X-Desk": "1"})
        self.assertIn("unknown supplier", r.text)

    def test_limits(self):
        gif = self.c.post("/desk/scan", files={"files": ("a.gif", b"GIF89a" + b"\0" * 20, "image/gif")}, headers={"X-Desk": "1"})
        self.assertEqual(gif.status_code, 415)
        big = self.c.post("/desk/scan", files={"files": ("a.jpg", JPG + b"\0" * (5 * 1024 * 1024), "image/jpeg")}, headers={"X-Desk": "1"})
        self.assertEqual(big.status_code, 413)
        self.assertEqual(self.c.post("/desk/scan", data={"sample": "B99"}, headers={"X-Desk": "1"}).status_code, 415)

    def test_unreadable_shows_reason(self):
        with mock.patch("app.services.desk.scan", side_effect=None, return_value={
                "id": "x/1", "batch": "x", "n": 1, "status": "unreadable", "label": "unreadable", "diffs": [], "stamps": [],
                "reason": "model is off on this server", "readers": [{"name": "m", "ok": False, "error": "model is off", "fields": []}] * 2}):
            r = self.c.post("/desk/scan", data={"sample": "B02"}, headers={"X-Desk": "1"})
        self.assertIn("model is off", r.text)
        self.assertIn("grey", r.text)

    def test_guard_answers_about_the_bill(self):
        rid = self.c.post("/runs?seed=1", follow_redirects=False).headers["location"].rsplit("/", 1)[-1]
        v = desk.scan("B07.jpg", (desk.intake.BILLS_DIR / "B07.jpg").read_bytes())
        ask = lambda q: self.c.post(f"/runs/{rid}/voice/ask", data={"text": q, "bill": v["id"]}, headers=HX).text
        self.assertIn("but the bill total says", ask("Why is this one on hold?"))
        self.assertIn("So this bill is on hold", ask("why is this one on hold"))
        self.assertEqual(sum(e["kind"] == "bill_confirmed" for e in state.CHAIN), 0)  # the desk never confirms


if __name__ == "__main__":
    unittest.main()
