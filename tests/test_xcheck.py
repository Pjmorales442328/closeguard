# tests/test_xcheck.py — second-model cross-check: prompt hides model 1's reasoning, disagreement forces an ack,
# off-schema and unavailable second model fail closed, and the committed bench cache replays offline.
import json
import tempfile
import unittest
from decimal import Decimal

from agent import xcheck
from agent.client import Client
from core.models import Approval, Decision, Proposal
from core.sod import check_approval
from tests.test_agent import FakeCall
from tests.test_matcher import load


def fake(*contents):
    return Client(call=FakeCall(*contents), model=xcheck.XCHECK_MODEL, fallback=None, cache_dir=tempfile.mkdtemp(),
                  backoff=0, retries=1)


class XcheckTest(unittest.TestCase):
    def setUp(self):
        self.bank, self.ledger = load()[:2]
        self.bmap, self.lmap = {b.txn_id: b for b in self.bank}, {l.inv_id: l for l in self.ledger}
        self.p = Proposal("B0078", ("INV-2037",), Decimal("1250.00"), {"INV-2037": Decimal("1250.00")}, "match",
                          "model confidence 0.90: looks like a partial payment")

    def test_second_model_is_different_and_never_sees_reasoning(self):
        from agent.client import MODEL
        self.assertNotEqual(xcheck.XCHECK_MODEL, MODEL)
        msgs = xcheck.review_messages(self.bmap["B0078"], [self.lmap["INV-2037"]], self.p)
        self.assertNotIn("partial payment", json.dumps(msgs))
        self.assertNotIn("confidence", json.dumps(msgs))
        self.assertIn('"INV-2037"', msgs[1]["content"])

    def test_disagreement_flags_and_blocks_unacked_approval(self):
        c = fake('{"agree": false, "reason": "invoice is 1520.00"}')
        d = {"B0078": Decision("B0078", "allow", None, "passed")}
        out = xcheck.flag_decisions(d, [self.p], self.bmap, self.lmap, c)
        self.assertIn(xcheck.FLAG, out["B0078"].flag)
        maria = Approval("B0078", "Maria", "controller", "approve")
        self.assertEqual(check_approval(self.p, maria, out["B0078"].flag).rule, "policy.memo_unacknowledged")
        self.assertEqual(check_approval(self.p, Approval("B0078", "Maria", "controller", "approve", ack=True),
                                        out["B0078"].flag).result, "allow")

    def test_agreement_leaves_decision_unchanged_and_skips_non_model_or_refused(self):
        c = fake('{"agree": true, "reason": "fits"}')
        matcher_p = Proposal("B0001", ("INV-2001",), Decimal("1.00"), {"INV-2001": Decimal("1.00")}, "match", "exact")
        d = {"B0078": Decision("B0078", "allow", None, "passed"), "B0001": Decision("B0001", "allow", None, "passed"),
             "B0024": Decision("B0024", "refuse", "policy.evidence_missing", "x")}
        refused = Proposal("B0024", ("INV-2037",), Decimal("1.00"), {"INV-2037": Decimal("1.00")}, "match", "model confidence 0.5: x")
        out = xcheck.flag_decisions(d, [self.p, matcher_p, refused], self.bmap, self.lmap, c)
        self.assertEqual(out, d)
        self.assertEqual(len(c.call.calls), 1)  # only the allowed model match was reviewed

    def test_off_schema_and_unavailable_fail_closed(self):
        self.assertFalse(xcheck.parse_verdict({"agree": "yes", "reason": "r"})["agree"])
        self.assertFalse(xcheck.parse_verdict({"reason": "r"})["agree"])
        v = xcheck.review(fake("not json"), self.bmap["B0078"], [self.lmap["INV-2037"]], self.p)
        self.assertFalse(v["agree"])
        self.assertIn("unavailable", v["reason"])

    def test_committed_cache_replays_offline(self):
        from bench.xcheck import report, run
        r = run.run(live=False)
        self.assertEqual(r["real_calls_this_run"], 0)
        committed = json.loads((run.HERE / "results.json").read_text("utf-8"))
        for k in ("reviewed", "agree", "disagree", "disagreements_on_gate_allowed", "second_model"):
            self.assertEqual(r[k], committed[k])
        self.assertFalse([t for t in r["trials"] if "unavailable" in t["reason"]])
        self.assertIn("agreement rate", report.render(r))


class AppFlagTest(unittest.TestCase):
    def test_disagreement_shows_badge_and_needs_ack(self):
        """No seed-run model match passes the gate, so one matcher match is treated as model-proposed for this test."""
        import os
        from unittest import mock
        try:
            from fastapi.testclient import TestClient
            from app import state
            from app.main import app
        except ImportError:
            self.skipTest("fastapi not installed")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CG_", "VULTR_"))} | {"CG_MODEL_LIVE": "1"}
        c = fake('{"agree": false, "reason": "SECOND-MODEL-SAYS-NO"}')
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("agent.xcheck.client", lambda **kw: c),                 mock.patch("agent.xcheck.is_model_match", lambda p: p.txn_id == "B0002"),                 mock.patch("agent.client._openai_call", side_effect=AssertionError("network")):
            tc = TestClient(app)
            rid = tc.post("/runs?seed=1", follow_redirects=False).headers["location"].rsplit("/", 1)[-1]
            page = tc.get(f"/runs/{rid}").text
            no_ack = tc.post(f"/runs/{rid}/approve", data={"txn_id": "B0002", "approver": "Maria", "role": "controller"}).text
            acked = tc.post(f"/runs/{rid}/approve", data={"txn_id": "B0002", "approver": "Maria", "role": "controller", "ack": "true"}).text
        self.assertIn("second model disagrees", page)
        self.assertIn("SECOND-MODEL-SAYS-NO", page)
        self.assertIn("policy.memo_unacknowledged", no_ack)
        self.assertNotIn("policy.memo_unacknowledged", acked.split('<div class="console">')[0])  # flash; history keeps the refusal
        self.assertIn("B0002", {a.txn_id for a in state.RUNS[rid].approvals})


if __name__ == "__main__":
    unittest.main()
