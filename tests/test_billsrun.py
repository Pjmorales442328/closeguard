# tests/test_billsrun.py — bills-sized bank, model-call budget on every path, bills run off the event loop. No network.
import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import config
    from app.main import app
    from app.services import intake, intake_human, recorder
    from app.services import intake_read as ir
except ImportError:  # fastapi not installed in this interpreter
    app = None

ANSWER = {"content": '{"matches": [], "confidence": 0.4, "explanation": "no candidate fits"}', "usage": {"prompt": 10, "completion": 5}}
NO_NET = mock.Mock(side_effect=AssertionError("network call attempted"))


def msg(txn):
    return [{"role": "user", "content": json.dumps({"bank_line": {"txn_id": txn}, "n": txn})}]


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class BillsRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CG_", "VULTR_"))}
        env.update(CG_MODEL_LIVE="1", CG_RUNTIME_CACHE=self.tmp.name)
        for p in (mock.patch.dict(os.environ, env, clear=True), mock.patch("agent.client.CACHE_DIR", self.tmp.name)):
            p.start()
            self.addCleanup(p.stop)

    def test_generator_is_deterministic_and_committed(self):
        from data.bills_bank_gen import render
        self.assertEqual(config.BILLS_BANK_CSV.read_text("utf-8"), render())

    def fresh_demo(self):
        files = [(c.name, c.data) for c in intake.demo().cards]
        b = intake._make("t", files, False)
        intake.read_all(b)
        return b

    def test_demo_bills_run_from_cache_passes_clean_bills_and_holds_traps(self):
        b = self.fresh_demo()
        c = b.cards[12]
        truth = {"invoice_no": "FAL-24371", "due_date": "2026-11-02"}
        picks = {f: "0" if str(x) == truth[f] else "1" for f, x, _ in ir.pick_fields(c)}
        self.assertEqual(intake_human.confirm(b, c, "Maria", "controller", picks).result, "allow")
        with mock.patch("agent.client._openai_call", NO_NET):
            run = intake.make_run(b)
        self.assertEqual([x["how"] for x in run.model["calls"]], ["cached", "cached"])
        held = {t: d.rule for t, d in run.decisions.items() if d.result == "refuse"}
        self.assertEqual(held, {"BB004": "policy.duplicate_payment", "BB008": "policy.unknown_payee",
                                "BB009": "policy.evidence_missing", "BB012": "policy.part_mismatch"})
        self.assertEqual(run.counters()["allowed"], 8)
        page = TestClient(app).get(f"/runs/{run.id}").text
        self.assertIn("two AI readers read each bill", page)  # banner says which path ran
        self.assertNotIn("30 faults planted", page)

    def test_cache_path_caps_network_calls_and_says_so(self):
        call = mock.Mock(return_value=ANSWER)
        with mock.patch("agent.client._openai_call", call):
            rec = recorder.Recorder(live=False)
            for i in range(recorder.MAX_LIVE_CALLS + 3):
                try:
                    rec.complete_json(msg(f"T{i}"))
                except Exception as e:  # noqa: BLE001
                    self.assertIn("limit for this run reached", str(e))
        self.assertEqual(call.call_count, recorder.MAX_LIVE_CALLS)
        self.assertLessEqual(max(k["timeout"] for _, k in call.call_args_list), recorder.LIVE_TIMEOUT_S)
        self.assertEqual([c["how"] for c in rec.calls], ["live"] * recorder.MAX_LIVE_CALLS + ["skipped"] * 3)

    def test_wall_budget_stops_network_on_both_paths(self):
        for live in (False, True):
            with mock.patch("agent.client._openai_call", NO_NET):
                rec = recorder.Recorder(live=live)
                rec.deadline = time.monotonic() - 1
                with self.assertRaises(Exception):
                    rec.complete_json(msg("T-late"))
            self.assertEqual(rec.calls[-1]["how"], "skipped")

    def test_healthz_answers_while_a_bills_run_is_going(self):
        gate, done = threading.Event(), []

        def slow(*_a, **_k):
            gate.wait(10)
            raise intake.IntakeRefused("stopped by test")
        with TestClient(app) as c, mock.patch.object(intake, "make_run", slow):
            t = threading.Thread(target=lambda: done.append(c.post("/bills/demo/run").status_code))
            t.start()
            time.sleep(0.3)
            t0 = time.monotonic()
            self.assertEqual(c.get("/healthz").status_code, 200)
            self.assertLess(time.monotonic() - t0, 2)
            self.assertTrue(t.is_alive())  # the run is still in flight
            gate.set()
            t.join(10)
        self.assertEqual(done, [400])

    def test_kit_ships_its_own_bank_that_only_pays_kit_bills(self):
        import io
        import zipfile
        from data.bills_bank_gen import KIT_OUT, render
        z = zipfile.ZipFile(io.BytesIO(TestClient(app).get("/bills/kit.zip").content))
        self.assertEqual(z.read("bank_kit_2026-10.csv").decode("utf-8"), render(kit=True))
        self.assertEqual(KIT_OUT.read_text("utf-8"), render(kit=True))
        self.assertIn("bank_kit_2026-10.csv", z.read("README.txt").decode())
