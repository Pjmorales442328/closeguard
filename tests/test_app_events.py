# tests/test_app_events.py — event feed grouping, story pins, proposer labels, xcheck rows and /ledger.jsonl.
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
    from app.services import events
    from core import chain
except ImportError:  # fastapi not installed in this interpreter
    app = None

HX = {"HX-Request": "true"}
KEYS = {"seq", "seq_to", "at", "kind", "hash", "tone", "text", "sub", "short", "rule", "txns", "to", "actor", "n",
        "who", "story", "batch", "items"}


def _gate(txn, result="allow", kind="match", flag=None, rule=None):
    return {"run_id": "r1", "txn_id": txn, "inv_ids": [] if kind == "unmatched" else ["INV-1"], "amount": "10.00",
            "kind": kind, "proposer": "agent", "result": result, "rule": rule, "detail": "d", "flag": flag}


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class FeedUnitTest(unittest.TestCase):
    def feed(self, payloads, rationale=None):
        rationale = rationale or {}
        run = SimpleNamespace(id="r1", proposals=[SimpleNamespace(txn_id=p["txn_id"], rationale=rationale.get(
            p["txn_id"], "exact amount")) for k, p in payloads if k == "gate_decision"])
        ch = []
        for k, p in payloads:
            chain.append(ch, k, p)
        with mock.patch.object(state, "CHAIN", ch):
            return events.feed(run)

    def test_groups_allows_and_unmatched_but_never_refusals_flags_or_model(self):
        f = self.feed([("gate_decision", _gate("A1")), ("gate_decision", _gate("A2")),
                       ("gate_decision", _gate("R1", "refuse", rule="policy.over_cap")),
                       ("gate_decision", _gate("R2", "refuse", rule="policy.over_cap")),
                       ("gate_decision", _gate("A3")), ("gate_decision", _gate("F1", flag="memo_prose")),
                       ("gate_decision", _gate("M1")), ("gate_decision", _gate("U1", "refuse", "unmatched")),
                       ("gate_decision", _gate("U2", "refuse", "unmatched"))],
                      {"M1": "model confidence 0.90: fits"})
        self.assertEqual([(e["txns"], e["batch"]) for e in f],
                         [(["A1", "A2", "A3"], True), (["R1"], False), (["R2"], False), (["F1"], False),
                          (["M1"], False), (["U1", "U2"], True)])
        b = f[0]
        self.assertEqual((b["n"], b["seq"], b["seq_to"], b["tone"], b["to"]), (3, 1, 5, "allow", "waiting"))
        self.assertEqual([i["txns"] for i in b["items"]], [["A1"], ["A2"], ["A3"]])
        self.assertLessEqual(len(b["short"]), 32)
        self.assertIn("3 lines matched exactly", b["text"])

    def test_story_lines_pinned_and_never_grouped(self):
        f = self.feed([("gate_decision", _gate("A1")), ("gate_decision", _gate("B0009")), ("gate_decision", _gate("A2"))])
        self.assertEqual([(e["txns"], e["story"]) for e in f], [(["A1", "A2"], False), (["B0009"], True)])

    def test_who_labels(self):
        f = self.feed([("gate_decision", _gate(t, "refuse", rule="policy.x")) for t in ("M", "S", "D")],
                      {"M": "model confidence 0.80: x", "S": "model stand-in (offline bait)"})
        self.assertEqual([e["who"] for e in f], ["model", "stand-in", "matcher"])
        self.assertTrue(f[0]["sub"].startswith("The AI matched"))
        self.assertTrue(f[1]["sub"].startswith("The practice stand-in matched"))
        self.assertNotIn("The AI matched", f[1]["sub"])

    def test_xcheck_disagreement_is_its_own_row(self):
        flag = "memo_prose; second model disagrees (qwen3.8-27b): vendor differs"
        f = self.feed([("gate_decision", _gate("M1", flag=flag))], {"M1": "model confidence 0.9: x"})
        self.assertEqual([e["kind"] for e in f], ["gate_decision", "xcheck_disagree"])
        self.assertEqual(f[1]["sub"], "second model disagrees (qwen3.8-27b): vendor differs")
        self.assertTrue(set(f[1]) >= KEYS)


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class FeedAppTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env["CG_ATTEMPTS"] = os.path.join(self.tmp.name, "attempts.jsonl")
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.c = TestClient(app)
        rid = self.c.post("/runs?seed=1", follow_redirects=False).headers["location"].rsplit("/", 1)[-1]
        self.run = state.RUNS[rid]
        self.c.post(f"/runs/{rid}/approve", data={"txn_id": "*", "approver": "agent", "role": "agent"}, headers=HX)
        self.c.post(f"/runs/{rid}/approve", data={"txn_id": "*", "approver": "Maria", "role": "controller"}, headers=HX)
        self.c.post(f"/runs/{rid}/post", headers=HX)

    def test_full_seed_feed(self):
        f = events.feed(self.run)
        self.assertLessEqual(len(f), 40)
        for e in f:
            self.assertTrue(set(e) >= KEYS, e["kind"])
            self.assertLessEqual(len(e["short"]), 32)
        refused = [e for e in f if e["kind"] == "gate_decision" and e["tone"] == "refuse"]
        self.assertEqual(len(refused), 30)  # every gate refusal keeps its own row
        self.assertTrue(all(not e["batch"] for e in refused))
        self.assertEqual({t for e in f if e["story"] for t in e["txns"]}, events.STORY)
        gate_txns = [t for e in f if e["kind"] == "gate_decision" for t in e["txns"]]
        self.assertEqual(sorted(gate_txns), sorted(self.run.bank))  # nothing lost or doubled by grouping
        self.assertEqual([e["kind"] for e in f[-3:]], ["approval", "post", "verify_db"])
        self.assertFalse(any(e["who"] == "model" for e in f))  # offline seed run: stand-ins only, never "Model"

    def test_ledger_jsonl_matches_verify(self):
        r = self.c.get("/ledger.jsonl")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith("application/x-ndjson"))
        entries = [json.loads(line) for line in r.text.splitlines()]
        v = self.c.get("/ledger/verify").json()
        self.assertEqual(chain.verify(entries), v)
        self.assertTrue(v["ok"])
        self.assertEqual(entries[-1]["hash"], state.CHAIN[-1]["hash"])
        self.assertNotIn("VULTR", r.text)
