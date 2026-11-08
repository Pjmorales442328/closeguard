"""Demo month: no bank statement until Ana imports one; a bad file is refused in plain words; Clear forgets it."""
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.services import bank_import


class BankImport(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(app)
        bank_import.clear()

    def test_demo_starts_without_a_statement_and_imports_one(self):
        with mock.patch.dict(os.environ, {"CG_SEED_DEMO": "1"}):
            self.assertIsNone(bank_import.rows())
            self.assertFalse(self.c.get("/app/state").json()["bank"]["imported"])
            r = self.c.post("/app/bank/import", data={"sample": "1"})
            self.assertEqual(r.status_code, 200, r.text)
            k = self.c.get("/app/state").json()["bank"]
            self.assertTrue(k["imported"]); self.assertGreater(k["count"], 0)
            self.c.post("/stage/clear")
            self.assertIsNone(bank_import.rows())

    def test_bad_file_is_refused(self):
        r = self.c.post("/app/bank/import", files={"file": ("x.csv", b"hello,world\n1,2\n", "text/csv")})
        self.assertEqual(r.status_code, 422)
        self.assertIn("not a bank statement", r.json()["error"])

    def test_real_csv_upload(self):
        from app import config
        r = self.c.post("/app/bank/import", files={"file": ("oct.csv", config.BILLS_BANK_CSV.read_bytes(), "text/csv")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(bank_import.name(), "oct.csv")


if __name__ == "__main__":
    unittest.main()
