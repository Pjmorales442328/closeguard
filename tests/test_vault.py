# tests/test_vault.py — the month's proof pack: every file fingerprinted, audit trail intact, photos in, the save chained; S3 faked.
import hashlib
import io
import json
import os
import time
import unittest
import zipfile
from unittest import mock

try:
    from fastapi.testclient import TestClient
    from app import state
    from app.main import app
    from app.services import signin, vault, vault_s3
except ImportError:  # fastapi not installed in this interpreter
    app = None

S3 = {"CG_S3_ENDPOINT": "https://ewr1.vultrobjects.com", "CG_S3_ACCESS_KEY": "AK", "CG_S3_SECRET_KEY": "SK", "CG_S3_BUCKET": "b"}


@unittest.skipIf(app is None, "fastapi/httpx not installed (pip install -r requirements.txt)")
class VaultTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CG_")}
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        self.c = TestClient(app)
        self.c.post("/stage/clear")
        signin._fails.clear()
        vault._CACHE["v"] = None
        for k in ("R01", "R04"):
            jid = self.c.post("/stage/scan", data={"sample": k}).json()["job"]
            for _ in range(300):
                if self.c.get(f"/stage/job/{jid}").json()["done"]:
                    break
                time.sleep(0.02)

    def test_pack_fingerprints_every_file(self):
        data, man = vault.build()
        z = zipfile.ZipFile(io.BytesIO(data))
        self.assertEqual(json.loads(z.read("manifest.json")), json.loads(json.dumps(man)))
        for path, f in man["files"].items():
            self.assertEqual(hashlib.sha256(z.read(path)).hexdigest(), f["sha256"])
        self.assertTrue(man["audit_trail"]["intact"])
        self.assertTrue(man["synthetic_data"])
        self.assertEqual(sum(p.startswith("bills/") for p in man["files"]), 2)  # both scanned photos
        bills = json.loads(z.read("bills.json"))
        self.assertTrue(all(len(b["readings"]) == 2 for b in bills))  # both readers, with their metadata

    def test_save_uploads_and_chains(self):
        put = mock.Mock()
        with mock.patch.dict(os.environ, S3), mock.patch.object(vault_s3, "ensure_bucket"), mock.patch.object(vault_s3, "put", put), \
                mock.patch.object(vault_s3, "list_keys", return_value=[("proof/2026-10/x.zip", 4096, "2026-11-07T12:00:00Z")]), \
                mock.patch.object(vault_s3, "exists", lambda c, k: put.called and k == put.call_args.args[1]):
            self.assertIn("Wrong PIN", self.c.post("/app/report/vault", data={"pin": "0000"}).text)  # it holds the QuickBooks file
            put.assert_not_called()
            r = self.c.post("/app/report/vault", data={"pin": "2468"})
            self.assertIn("Saved ", r.text)
            self.assertNotIn("X-Amz-Signature=", r.text)  # no download links on the page
            self.assertIn("Wrong PIN", self.c.post("/app/report/vault/get", data={"name": "x.zip", "pin": "0000"}).text)
            self.assertIn("no such proof file", self.c.post("/app/report/vault/get", data={"name": "../x.zip", "pin": "2468"}).text)
            name = put.call_args.args[1].rsplit("/", 1)[-1]
            d = self.c.post("/app/report/vault/get", data={"name": name, "pin": "2468"}, follow_redirects=False)
            self.assertIn("X-Amz-Signature=", d.headers["location"])  # 5-minute signed link, straight from Object Storage
            self.assertEqual(state.CHAIN[-1]["kind"], "evidence_downloaded")
            fake = {"name": "2026-01-01T000000Z-deadbeef.zip", "pin": "2468"}
            self.assertIn("no such proof file", self.c.post("/app/report/vault/get", data=fake).text)  # made-up name: no download logged
            self.assertEqual(state.CHAIN[-1]["kind"], "evidence_downloaded")
        key, body, ctype = put.call_args.args[1:]
        self.assertTrue(key.startswith("proof/2026-10/") and key.endswith(".zip"))
        self.assertEqual(ctype, "application/zip")
        e = next(e for e in reversed(state.CHAIN) if e["kind"] == "evidence_saved")
        self.assertEqual(e["payload"]["key"], key)
        self.assertEqual(e["payload"]["sha256"], hashlib.sha256(body).hexdigest())

    def test_storage_error_is_shown_not_raised(self):
        with mock.patch.dict(os.environ, S3), mock.patch.object(vault_s3, "ensure_bucket", side_effect=vault_s3.VaultError("Object Storage unreachable")), \
                mock.patch.object(vault_s3, "list_keys", return_value=[]):
            r = self.c.post("/app/report/vault", data={"pin": "2468"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Object Storage unreachable", r.text)
        self.assertNotEqual(state.CHAIN[-1]["kind"], "evidence_saved")

    def test_not_configured(self):
        self.assertIn("Object Storage is not set up", self.c.get("/app/report").text)


if __name__ == "__main__":
    unittest.main()
