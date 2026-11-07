# tests/test_gen.py — generator is idempotent (same bytes twice) and the committed files match a fresh run.
import hashlib
import tempfile
import unittest
from pathlib import Path

from data.gen import OUT, write

FILES = ("bank_2026-10.csv", "ledger_2026-10.csv", "faults.json", "README.md")


def digests(folder: Path):
    return {f: hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in FILES}


class GenTest(unittest.TestCase):
    def test_idempotent_and_committed_files_current(self):
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            w, faults = write(Path(t1))
            write(Path(t2))
            self.assertEqual(digests(Path(t1)), digests(Path(t2)))
            self.assertEqual(digests(Path(t1)), digests(OUT), "run `python -m data.gen` and commit")
        self.assertEqual(len(w.bank), 80)
        self.assertEqual(len(faults), 30)
        self.assertEqual(len(w.legit), 10)
        self.assertTrue(all(r["memo"].startswith("SYNTHETIC") for r in w.bank))


if __name__ == "__main__":
    unittest.main()
