# tests/test_heldout.py — held-out datasets are well-formed and the runner is deterministic (score is NOT asserted).
import json
import unittest

from bench.heldout import run as h, run_b


class HeldoutTest(unittest.TestCase):
    def test_datasets_well_formed(self):
        atk, leg = h.load("attacks.json"), h.load("legit.json")
        self.assertGreaterEqual(len(atk), 75)
        self.assertGreaterEqual(len(leg), 75)
        for rows in (atk, leg):
            ids = [r["id"] for r in rows]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertTrue(all(isinstance(r["text"], str) and r["text"] for r in rows))
        self.assertTrue(all(r["cls"] for r in atk))
        self.assertGreaterEqual(len({r["cls"] for r in atk}), 10)
        self.assertFalse({r["text"] for r in atk} & {r["text"] for r in leg})

    def test_set_b_well_formed_and_disjoint(self):
        # Set B is scored once, after the memo fix; this test never runs the gate on it.
        atk, leg = h.load("attacks.json", run_b.SET_B), h.load("legit.json", run_b.SET_B)
        self.assertGreaterEqual(len(atk), 80)
        self.assertGreaterEqual(len(leg), 80)
        self.assertGreaterEqual(len({r["cls"] for r in atk}), 14)
        for rows in (atk, leg):
            self.assertEqual(len({r["id"] for r in rows}), len(rows))
            self.assertTrue(all(isinstance(r["text"], str) and r["text"] for r in rows))
        old = {r["text"].casefold() for f in ("attacks.json", "legit.json") for r in h.load(f)}
        new = [r["text"].casefold() for r in atk + leg]
        self.assertEqual(len(new), len(set(new)))
        self.assertFalse(set(new) & old)

    def test_runner_deterministic_and_complete(self):
        r1, r2 = h.run(), h.run()
        self.assertEqual(json.dumps(r1, sort_keys=True), json.dumps(r2, sort_keys=True))
        a, g = r1["attacks"], r1["legit"]
        self.assertEqual(a["blocked"] + a["flagged"] + a["passed"], a["trials"])
        self.assertEqual(len(a["passes"]), a["passed"])
        self.assertEqual(len(a["flagged_list"]), a["flagged"])
        self.assertEqual(g["trials"], 2 * g["strings"])
        self.assertEqual(g["refused"] + g["flagged"] + g["clean"], g["trials"])
        self.assertTrue(r1["synthetic"])
        self.assertIn("## Every false refusal", h.md(r1))


if __name__ == "__main__":
    unittest.main()
