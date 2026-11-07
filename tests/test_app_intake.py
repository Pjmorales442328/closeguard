# tests/test_app_intake.py — bills in: upload limits, two-reader statuses, SoD on confirm, chained events, run from bills. No network.
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

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64
RAW = {"supplier": "Birch Logistics", "invoice_no": "BIR-87397", "invoice_date": "2026-10-03", "due_date": "2026-11-02",
       "currency": "USD", "total": "2979.29", "line_items": [{"description": "a", "amount": "2979.29"}], "notes": ""}
META = {"latency_s": 1.0, "cached": True}


def extract_models():
    from agent.extract import MODELS
    return MODELS


def readings(a=None, b=None):
    return lambda image, mime, clients=None: [(a or RAW, META), (b or a or RAW, META)]


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class IntakeAppTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        self.c = TestClient(app)

    def upload(self, files, two=None):
        with mock.patch("agent.extract.two_readings", two or readings()):
            r = self.c.post("/bills", files=[("files", (n, d, "image/png")) for n, d in files], follow_redirects=False)
            if r.status_code == 303:
                intake.BATCHES[r.headers["location"].split("=")[1]].thread.join(10)
        return r

    def batch(self, r):
        return intake.BATCHES[r.headers["location"].split("=")[1]]

    def test_good_png_becomes_a_ready_card(self):
        r = self.upload([("a.png", PNG)])
        self.assertEqual(r.status_code, 303)
        self.assertEqual(self.batch(r).cards[0].status, "ready")
        self.assertIn("agreed, checks pass", self.c.get(r.headers["location"]).text)

    def test_upload_limits_are_400s(self):
        for files in ([("a.gif", b"GIF89a" + b"0" * 40)], [("big.png", PNG + b"0" * (5 * 1024 * 1024))],
                      [(f"{i}.png", PNG) for i in range(11)], []):
            self.assertEqual(self.upload(files).status_code, 400, files[:1])

    def disagreeing(self):
        other = {**RAW, "total": "2979.28", "line_items": [{"amount": "2979.28"}], "supplier": "Birch Logistics Ltd"}
        b = self.batch(self.upload([("a.png", PNG)], readings(RAW, other)))
        return b, b.cards[0], f"/bills/{b.id}/1/confirm"

    def test_disagreement_waits_for_a_human_and_agent_cannot_confirm(self):
        b, c, url = self.disagreeing()
        self.assertEqual((c.status, c.diffs), ("confirm", ["supplier", "total", "line_items"]))
        ok = {"pick_supplier": "0", "pick_total": "0", "pick_line_items": "0"}
        n = len(state.CHAIN)
        self.assertEqual(self.c.post(url, data={"who": "agent", "role": "controller", **ok}).status_code, 403)
        self.assertEqual(self.c.post(url, data={"who": "Ana", "role": "analyst", **ok}).status_code, 403)
        self.assertEqual(c.status, "confirm")
        refusals = [e for e in state.CHAIN[n:] if e["kind"] == "bill_confirmed"]
        self.assertEqual([e["payload"]["result"] for e in refusals], ["refuse", "refuse"])
        self.assertEqual(refusals[0]["payload"]["rule"], "policy.segregation_of_duties")
        done = self.c.post(url, data={"who": "Maria", "role": "controller", **ok}, follow_redirects=False)
        self.assertEqual((done.status_code, c.status), (303, "confirmed"))

    def test_every_differing_field_must_be_picked_and_chain_records_each_pick(self):
        b, c, url = self.disagreeing()
        n = len(state.CHAIN)
        r = self.c.post(url, data={"who": "Maria", "role": "controller", "pick_total": "0", "pick_line_items": "0"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("choose a value for supplier", r.text)
        self.assertEqual(c.status, "confirm")
        data = {"who": "Maria", "role": "controller", "pick_supplier": "1", "pick_total": "other", "other_total": "2979.29",
                "pick_line_items": "0", "pick_invoice_no": "other", "other_invoice_no": "ignored: not a differing field"}
        self.assertEqual(self.c.post(url, data=data, follow_redirects=False).status_code, 303)
        m = c.merged
        self.assertEqual((m.supplier, str(m.total), m.invoice_no), ("Birch Logistics Ltd", "2979.29", "BIR-87397"))
        last = [e for e in state.CHAIN[n:] if e["kind"] == "bill_confirmed"][-1]["payload"]
        self.assertEqual(last["sources"], {"supplier": extract_models()[1], "total": "typed", "line_items": extract_models()[0]})
        self.assertEqual((last["who"], last["values"]["total"]), ("Maria", "2979.29"))

    def test_typed_value_is_strictly_validated_and_merged_bill_is_rechecked(self):
        b, c, url = self.disagreeing()
        base = {"who": "Maria", "role": "controller", "pick_supplier": "0", "pick_line_items": "0"}
        bad = self.c.post(url, data={**base, "pick_total": "other", "other_total": "12.345"})
        self.assertEqual(bad.status_code, 403)
        self.assertIn("intake.pick_invalid", bad.text)
        mixed = self.c.post(url, data={**base, "pick_total": "1"})  # total 2979.28 but lines add up to 2979.29
        self.assertEqual(mixed.status_code, 403)
        self.assertIn("intake.checks_failed", mixed.text)
        self.assertIn("intake.line_sum", mixed.text)
        self.assertEqual((c.status, c.merged), ("confirm", None))

    def test_one_unreadable_reader_means_accept_that_reading_as_a_whole(self):
        two = lambda image, mime, clients=None: [(RAW, META), (None, {"error": "model gave no usable answer"})]  # noqa: E731
        b = self.batch(self.upload([("a.png", PNG)], two))
        c = b.cards[0]
        self.assertEqual((c.status, c.diffs), ("confirm", ["one reader unreadable"]))
        self.assertEqual(self.c.post(f"/bills/{b.id}/1/confirm", data={"who": "Maria", "role": "controller", "reading": 1}).status_code, 403)
        ok = self.c.post(f"/bills/{b.id}/1/confirm", data={"who": "Maria", "role": "controller", "reading": 0}, follow_redirects=False)
        self.assertEqual((ok.status_code, c.status, str(c.merged.total)), (303, "confirmed", "2979.29"))

    def test_failed_check_cannot_be_confirmed_and_run_uses_only_good_rows(self):
        bad = {**RAW, "invoice_no": "BIR-2", "total": "10.00"}  # lines add up to 2979.29, total says 10.00
        r = self.upload([("a.png", PNG)])
        b = intake.receive([("b.png", PNG), ("c.png", PNG)])
        with mock.patch("agent.extract.two_readings", side_effect=[[(RAW, META)] * 2, [(bad, META)] * 2]):
            intake.read_all(b)
        self.assertEqual([c.status for c in b.cards], ["ready", "refused"])
        self.assertEqual(self.c.post(f"/bills/{b.id}/2/confirm", data={"who": "Maria", "role": "controller"}).status_code, 403)
        run = intake.make_run(b)
        self.assertEqual(list(run.ledger), ["BILL-001"])
        self.assertIn("ledger from 1 bill images", run.source)
        self.assertTrue(run.uploaded)  # visitor images: unlisted, memory-only run
        self.assertEqual(self.batch(r).cards[0].status, "ready")

    def test_run_endpoint_redirects_and_empty_batch_is_400(self):
        r = self.upload([("a.png", PNG)])
        b = self.batch(r)
        ok = self.c.post(f"/bills/{b.id}/run", follow_redirects=False)
        self.assertEqual((ok.status_code, ok.headers["location"].startswith("/runs/")), (303, True))
        b.cards[0].status = "refused"
        self.assertEqual(self.c.post(f"/bills/{b.id}/run").status_code, 400)

    def test_demo_batch_loads_from_committed_cache_without_network(self):
        with mock.patch("agent.client._openai_call", side_effect=AssertionError("network")):
            page = self.c.get("/bills").text
        self.assertIn("agreed, checks pass", page)
        self.assertIn("refused by a check", page)
        self.assertIn("readers disagree: needs a person", page)
        self.assertEqual(self.c.get("/bills/kit.zip").headers["content-type"], "application/zip")

    def test_bills_run_never_uses_the_standin_baits(self):
        run = intake.make_run(intake.demo())
        self.assertFalse(run.uploaded)
        self.assertIn("no stand-in baits", run.source)
        self.assertFalse([p for p in run.proposals if "stand-in" in p.rationale or "stand-in" in p.proposer])
        self.assertTrue(all(i in run.ledger for p in run.proposals for i in p.inv_ids), "every cited invoice is a bill row")


if __name__ == "__main__":
    unittest.main()


class DemoReset(unittest.TestCase):
    def test_reset_gives_a_fresh_demo_batch(self):
        from app.services import intake
        first = intake.demo()
        intake.reset_demo()
        self.assertIsNot(first, intake.demo())
