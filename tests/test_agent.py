# tests/test_agent.py — network-free tests for agent/client.py and agent/propose.py using an injected fake call.
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from agent.client import Client, ModelError
from agent.propose import SYSTEM, narrate, parse_proposal, propose, propose_messages
from core.gate import run_gate
from core.matcher import match
from tests.test_matcher import load


class FakeCall:
    """Scripted responses: each call pops the next content string; counts calls."""

    def __init__(self, *contents):
        self.contents, self.calls = list(contents), []

    def __call__(self, model, messages, max_tokens):
        self.calls.append((model, messages, max_tokens))
        return {"content": self.contents.pop(0), "usage": {"prompt": 10, "completion": 5}}


def client(*contents, **kw):
    tmp = tempfile.mkdtemp()
    return Client(call=FakeCall(*contents), cache_dir=tmp, backoff=0, **kw), tmp


class ClientTest(unittest.TestCase):
    def test_valid_json(self):
        c, _ = client('{"a": 1}')
        self.assertEqual(c.complete_json([{"role": "user", "content": "x"}]), {"a": 1})
        self.assertFalse(c.last["cached"])
        self.assertGreaterEqual(c.max_tokens, 4000)

    def test_empty_content_retried(self):
        c, _ = client("", "   ", '{"ok": true}')
        self.assertEqual(c.complete_json([{"role": "user", "content": "x"}]), {"ok": True})
        self.assertEqual(len(c.call.calls), 3)

    def test_malformed_json_rejected_then_fallback_model(self):
        c, _ = client("not json", "[1,2]", "{", '{"from": "fallback"}', retries=3)
        self.assertEqual(c.complete_json([{"role": "user", "content": "x"}]), {"from": "fallback"})
        self.assertEqual([m for m, _, _ in c.call.calls], ["glm-5.3-flash"] * 3 + ["qwen3.8-27b"])

    def test_all_attempts_fail_raises(self):
        c, _ = client(*["nope"] * 6)
        with self.assertRaises(ModelError):
            c.complete_json([{"role": "user", "content": "x"}])

    def test_cache_hit_on_second_call(self):
        c, tmp = client('{"n": 1}')
        msgs = [{"role": "user", "content": "same"}]
        self.assertEqual(c.complete_json(msgs), {"n": 1})
        self.assertEqual(c.complete_json(msgs), {"n": 1})  # FakeCall would IndexError if called again
        self.assertTrue(c.last["cached"])
        self.assertEqual(len(list(Path(tmp).glob("*.json"))), 1)


class ProposeTest(unittest.TestCase):
    def test_bait_lines_proposed_then_refused_by_gate(self):
        bank, ledger, faults = load()
        baits = {f["txn_id"]: f for f in faults["faults"] if f["bait"]}
        props = match(bank, ledger)
        answers = [json.dumps({"matches": [{"inv_id": i, "amount": baits[p.txn_id]["bait"]["amount"]}
                                           for i in baits[p.txn_id]["bait"]["inv_ids"]],
                               "confidence": 0.9, "explanation": "looks right"})
                   for p in props if p.kind == "unmatched"]
        c, _ = client(*answers)
        out = propose(props, bank, ledger, c)
        self.assertEqual(len(out), len(bank))
        self.assertFalse([p for p in out if p.kind == "unmatched"])
        d = {x.txn_id: x for x in run_gate(out, {b.txn_id: b for b in bank}, {l.inv_id: l for l in ledger})}
        for t, f in baits.items():
            self.assertEqual((d[t].result, d[t].rule), ("refuse", f.get("expect_bait", f["expect"])), t)

    def test_memo_injection_is_data_and_cannot_widen_schema(self):
        bank, ledger, _ = load()
        b = next(x for x in bank if "ignore policy" in x.memo)
        msgs = propose_messages(b, ledger[:3])
        self.assertIn("untrusted DATA", msgs[0]["content"])
        self.assertEqual(msgs[0]["content"], SYSTEM)
        self.assertIn(b.memo, msgs[1]["content"])  # memo travels inside the JSON data payload only
        for data in ({"approved": True, "post": True}, {"matches": "all", "confidence": 1, "explanation": "ok"},
                     {"matches": [{"inv_id": "INV-2001", "amount": "1.0e3"}], "confidence": 2, "explanation": ""},
                     {"matches": [{"inv_id": "INV-2001", "amount": 12.5}], "confidence": 0.5, "explanation": ""}):
            p = parse_proposal(b.txn_id, b.amount, data)
            self.assertEqual((p.kind, p.inv_ids, p.amount), ("unmatched", (), b.amount), data)
            self.assertIn("rejected", p.rationale)

    def test_committed_seed_cache_replays_without_network(self):
        """The real glm-5.3-flash answers live in agent/cache; the model's partial payment on B0078 must hit rule 11."""
        bank, ledger, _ = load()

        def no_network(model, messages, max_tokens):
            raise AssertionError("seed cache miss: network call attempted")

        out = propose(match(bank, ledger), bank, ledger, Client(call=no_network))
        d = {x.txn_id: x for x in run_gate(out, {b.txn_id: b for b in bank}, {l.inv_id: l for l in ledger})}
        self.assertEqual((d["B0078"].result, d["B0078"].rule), ("refuse", "policy.part_mismatch"))
        self.assertEqual(sum(x.result == "allow" for x in d.values()), 50)

    def test_valid_split_parsed(self):
        p = parse_proposal("B1", Decimal("30.00"), {"matches": [{"inv_id": "A", "amount": "10.00"},
                                                                {"inv_id": "B", "amount": "20.00"}],
                                                    "confidence": 0.8, "explanation": "two invoices"})
        self.assertEqual((p.kind, p.inv_ids, p.amount, p.parts), ("split", ("A", "B"), Decimal("30.00"),
                                                                  {"A": Decimal("10.00"), "B": Decimal("20.00")}))

    def test_narrate_validates_and_falls_back(self):
        bank, ledger, _ = load()
        allowed = [p for p in match(bank, ledger) if p.kind == "match"][:2]
        c, _ = client('{"narrative": "Paid the October invoice."}', '{"narrative": "bad\nmultiline"}')
        out = narrate(allowed, bank, ledger, c)
        self.assertEqual(out[allowed[0].txn_id], "Paid the October invoice.")
        self.assertTrue(out[allowed[1].txn_id].startswith("Payment of "))


if __name__ == "__main__":
    unittest.main()
