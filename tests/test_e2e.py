# tests/test_e2e.py — e2e injection results are well-formed and the committed cache replays offline (no network).
import json
import unittest

from bench.e2e import report, run


class E2ETest(unittest.TestCase):
    def test_trials_well_formed(self):
        ts = run.trials()
        self.assertEqual(len({(t["id"], t["field"]) for t in ts}), len(ts))
        self.assertTrue({t["line"] for t in ts} <= set(run.LINES))
        self.assertLessEqual(len(ts) + (len(run.LINES) + 1) * run.REPEATS, run.MAX_CALLS)

    def test_cache_replays_offline_and_matches_committed(self):
        r = run.run(live=False)
        self.assertEqual(r["real_calls_this_run"], 0)
        committed = json.loads((run.HERE / "results.json").read_text("utf-8"))
        strip = lambda d: [{k: v for k, v in t.items() if k != "usage"} for t in d["trials"]]  # noqa: E731
        self.assertEqual(strip(r), strip(committed))
        self.assertFalse([t for t in r["trials"] if t["kind"] == "error"])

    def test_report_counts_consistent(self):
        r, labels = report.load()
        s = report.score(r, labels)
        tot = s["total"]
        self.assertEqual(tot["trials"], len(r["trials"]))
        self.assertLessEqual(tot.get("wrong_allow", 0), tot.get("hijack", 0))
        self.assertTrue(set(labels) <= {report.tid(t) for t in r["trials"]})


if __name__ == "__main__":
    unittest.main()
