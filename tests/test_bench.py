# tests/test_bench.py — offline: result schema, determinism (same sha256 without timing), ablation > 0, attacks counted.
import hashlib
import json
import unittest

from bench import attacks
from bench.run import run

KEYS = {"synthetic", "seed", "run_at", "model", "model_mode", "gate", "faults", "metrics", "ablation", "proposals",
        "cost", "timing", "human_baseline", "attacks", "model_unavailable_txns"}


def digest(r: dict) -> str:
    stable = {k: v for k, v in r.items() if k not in ("timing", "run_at")}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class BenchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r1, cls.r2 = run(), run()

    def test_schema(self):
        r = self.r1
        self.assertEqual(set(r), KEYS)
        self.assertEqual(len(r["faults"]), 30)
        self.assertEqual(set(r["faults"][0]), {"id", "type", "txn_id", "expected", "actual", "refused", "caught", "detail"})
        self.assertEqual(r["metrics"]["lines"], 80)
        self.assertEqual(r["model_unavailable_txns"], [], "cache miss: bench must run offline from the committed cache")
        self.assertIn("source", r["cost"]["price"])

    def test_deterministic(self):
        self.assertEqual(digest(self.r1), digest(self.r2))

    def test_ablation_positive(self):
        self.assertGreater(self.r1["ablation"]["faulty_proposals_reaching_controller"], 0)

    def test_attacks_all_counted(self):
        k = self.r1["attacks"]
        n = sum(len(v) for v in attacks.ATTACKS.values())
        self.assertGreaterEqual(n, 90)
        self.assertEqual(k["total"], 2 * n)
        self.assertEqual(k["blocked"] + k["flagged"] + k["passed"], k["total"])
        self.assertEqual(len(k["passes"]), k["passed"])
        self.assertEqual(len(k["flags"]), k["flagged"])
        self.assertEqual(k["downstream_controls"]["post_without_approval"], "policy.unapproved_post")

    def test_gate_off_lets_faults_through(self):
        off = run("off")
        self.assertGreater(off["metrics"]["fn"], 0)

class IntakeBenchTest(unittest.TestCase):
    def test_intake_json_matches_a_fresh_offline_run_and_readme(self):
        import json
        from pathlib import Path
        from bench import intake
        fresh, saved = intake.run(), json.loads((intake.OUT / "intake.json").read_text("utf-8"))
        for k in ("bills", "traps", "fields", "per_model", "agreement", "traps_detail", "clean_passed", "calls", "cached"):
            self.assertIn(k, saved)
            self.assertEqual(fresh[k], saved[k], k)
        self.assertEqual(saved["cached"], saved["calls"], "intake bench must run from the committed cache")
        self.assertIn(intake.markdown(saved), (intake.ROOT / "README.md").read_text("utf-8"))

if __name__ == "__main__":
    unittest.main()
