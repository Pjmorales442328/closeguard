# tests/test_integration.py — app + real agent/ + committed seed cache, with the network transport forced to fail.
import os
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
except ImportError:  # fastapi not installed in this interpreter
    app = None


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class CachedModelRunTest(unittest.TestCase):
    def test_seed_run_replays_cache_without_network_or_key(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CG_", "VULTR_"))}
        env["CG_MODEL_LIVE"] = "1"
        boom = mock.Mock(side_effect=AssertionError("network call attempted"))
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("agent.client._openai_call", boom):
            c = TestClient(app)
            r = c.post("/runs?seed=1", follow_redirects=False)
            run = state.RUNS[r.headers["location"].rsplit("/", 1)[-1]]
            page = c.get(f"/runs/{run.id}").text
            health = c.get("/healthz").json()
        boom.assert_not_called()
        self.assertEqual((run.counters()["allowed"], run.counters()["refused"]), (50, 30))
        d = run.decisions["B0078"]
        self.assertEqual((d.result, d.rule), ("refuse", "policy.part_mismatch"))
        self.assertIn("replayed from cache", run.source)
        self.assertIn("saved answers replayed", page)
        self.assertNotIn("baits", page)
        self.assertTrue(health["model"].startswith("model"))


if __name__ == "__main__":
    unittest.main()
