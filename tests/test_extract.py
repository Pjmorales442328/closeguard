# tests/test_extract.py — two-reader extraction with a fake transport: no network, no key.
import os
import tempfile
import unittest
from decimal import Decimal
from unittest import mock

from agent import extract
from agent.client import Client

GOOD = ('{"supplier": "Birch Logistics", "invoice_no": "BIR-1", "invoice_date": "2026-10-03", "due_date": "2026-11-02", '
        '"currency": "USD", "total": 10.50, "line_items": [{"description": "x", "amount": "10.50"}], "notes": ""}')
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


def clients(tmp, outputs, seen):
    def make(model):
        def call(m, msgs, max_tokens):
            seen.append((m, msgs))
            return {"content": outputs[m], "usage": {"prompt": 1, "completion": 1}}
        return Client(call=call, model=model, fallback=None, cache_dir=os.path.join(tmp, model), retries=1, backoff=0)
    return {m: make(m) for m in extract.MODELS}


class ExtractTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        p = mock.patch.dict(os.environ, {**env, "CG_MODEL_LIVE": "1"}, clear=True)
        p.start()
        self.addCleanup(p.stop)
        g = mock.patch("agent.client._openai_call", side_effect=AssertionError("network"))
        g.start()
        self.addCleanup(g.stop)

    def test_both_models_read_with_data_uri_and_decimal_amounts(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            a, b = extract.two_readings(PNG, "image/png", clients(tmp, {m: GOOD for m in extract.MODELS}, seen))
        self.assertEqual(sorted(m for m, _ in seen), sorted(extract.MODELS))
        for _, msgs in seen:
            self.assertTrue(msgs[1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(a[0]["total"], Decimal("10.50"))
        self.assertIs(type(a[0]["total"]), Decimal)
        self.assertFalse(a[1]["cached"])

    def test_non_json_from_one_model_is_unreadable_for_that_model_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = extract.two_readings(PNG, "image/png", clients(tmp, {extract.MODELS[0]: GOOD, extract.MODELS[1]: "sorry"}, []))
        self.assertIsNotNone(a[0])
        self.assertIsNone(b[0])
        self.assertIn("no usable answer", b[1]["error"])

    def test_model_off_and_no_cache_means_unreadable_without_a_call(self):
        seen = []
        with mock.patch.dict(os.environ, {"CG_MODEL_LIVE": "0"}), tempfile.TemporaryDirectory() as tmp:
            raw, meta = extract.read(PNG, "image/png", extract.MODELS[0], clients(tmp, {m: GOOD for m in extract.MODELS}, seen)[extract.MODELS[0]])
        self.assertIsNone(raw)
        self.assertEqual(seen, [])
        self.assertIn("model is off", meta["error"])

    def test_cache_hit_needs_no_switch_and_rate_limit_blocks_live(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            cs = clients(tmp, {m: GOOD for m in extract.MODELS}, seen)
            extract.read(PNG, "image/png", extract.MODELS[0], cs[extract.MODELS[0]])
            with mock.patch.dict(os.environ, {"CG_MODEL_LIVE": "0"}):
                raw, meta = extract.read(PNG, "image/png", extract.MODELS[0], cs[extract.MODELS[0]])
            self.assertTrue(meta["cached"])
            with mock.patch("agent.extract._allow_live", return_value=False):
                raw, meta = extract.read(b"other", "image/png", extract.MODELS[0], cs[extract.MODELS[0]])
        self.assertIn("rate limit", meta["error"])


if __name__ == "__main__":
    unittest.main()
