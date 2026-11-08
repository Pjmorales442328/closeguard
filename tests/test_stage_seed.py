# tests/test_stage_seed.py — demo server: the normal bills are pre-scanned at start and after Clear, never twice.
import os
import time
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services import stage_job
except ImportError:  # fastapi not installed in this interpreter
    app = None


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class SeedTest(unittest.TestCase):
    def wait(self):
        for _ in range(150):
            if len(stage_job.SCANNED) >= len(stage_job.SEED):
                time.sleep(0.5)  # a second seed, if any, would show up here
                break
            time.sleep(0.1)
        return len(stage_job.SCANNED)

    def test_seed_on_start_and_after_double_clear(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")} | {"CG_SEED_DEMO": "1", "CG_MODEL_LIVE": "0"}
        with mock.patch.dict(os.environ, env, clear=True), TestClient(app) as c:
            self.assertEqual(self.wait(), 6)
            c.post("/stage/clear"); c.post("/stage/clear")
            self.assertEqual(self.wait(), 6)
            c.post("/stage/clear")
        stage_job.clear()

    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {"CG_SEED_DEMO": ""}):
            stage_job.clear(); stage_job.seed(lambda k: None)
            self.assertEqual(stage_job.SCANNED, [])


if __name__ == "__main__":
    unittest.main()
