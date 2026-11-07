# app/services/vault.py — the month's proof pack, kept in Vultr Object Storage: bill photos, both AI readings with Vultr receipts,
# emails, the hash-chained audit trail and the QuickBooks file, in one zip with a SHA-256 per file. Survives restarts of the app.
import dataclasses
import hashlib
import io
import json
import re
import time
import zipfile

from app import state
from app.services import app_bank, books_export, intake, mail, runs, stage_job, vault_s3
from core import chain

MONTH = "2026-10"  # the demo's close period
PREFIX = f"proof/{MONTH}/"


def _j(obj) -> bytes:
    return json.dumps(obj, indent=1, default=str, ensure_ascii=False).encode()


def _bills() -> tuple:
    """(bill rows with readings and Vultr receipts, {zip path: image bytes})."""
    rows, images = [], {}
    for bid, n in list(stage_job.SCANNED):
        b = intake.get(bid)
        c = next((c for c in b.cards if c.n == n), None) if b else None
        if not c:
            continue
        path = f"bills/{c.bill_id.replace('/', '-')}{'.png' if c.mime == 'image/png' else '.jpg'}"
        images[path] = c.data
        rows.append({"bill_id": c.bill_id, "file": c.name, "photo": path, "photo_sha256": c.sha, "status": c.status, "confirmed_by": c.by or None,
                     "readings": [{"reading": dataclasses.asdict(r) if dataclasses.is_dataclass(r) else r, "reader": m} for r, m in zip(c.readings, c.metas)]})
    return rows, images


def build() -> tuple:
    """-> (zip bytes, manifest). Pure read of the current state; nothing is changed."""
    with state.LOCK:
        trail = [dict(e) for e in state.CHAIN]
    rows, images = _bills()
    files = {"audit-trail.json": _j(trail), "bills.json": _j(rows),
             "emails.json": _j([{k: t[k] for k in ("supplier", "to", "subject", "status", "msgs")} for t in mail.THREADS.values()])} | images
    run = runs.get_run(app_bank.LAST_RUN["id"]) if app_bank.LAST_RUN["id"] else None
    if run and run.posted:
        files["quickbooks-journal.csv"] = books_export.csv_text(run).encode()
    check = chain.verify(trail)
    manifest = {"what": "Closeguard month-end proof", "month": MONTH, "synthetic_data": True, "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "audit_trail": {"entries": check["length"], "intact": check["ok"], "last_hash": trail[-1]["hash"] if trail else chain.GENESIS},
                "files": {p: {"sha256": hashlib.sha256(d).hexdigest(), "bytes": len(d)} for p, d in sorted(files.items())}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", _j(manifest))
        for p, d in sorted(files.items()):
            z.writestr(p, d)
    return buf.getvalue(), manifest


def save(who: str) -> dict:
    """Upload the pack; the upload itself goes into the audit trail (key + SHA-256 of the zip). Raises VaultError."""
    c = vault_s3.conf()
    if not c:
        raise vault_s3.VaultError("Vultr Object Storage is not set up on this server")
    data, manifest = build()
    key = f"{PREFIX}{manifest['saved_at'].replace(':', '')}-{manifest['audit_trail']['last_hash'][:8]}.zip"
    vault_s3.ensure_bucket(c)
    vault_s3.put(c, key, data, "application/zip")
    out = {"key": key, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "files": len(manifest["files"]) + 1, "by": who,
           "store": f"Vultr Object Storage {c['endpoint'].split('//')[-1]}"}
    with state.LOCK:
        state.log("evidence_saved", out)
    _CACHE["v"], _CACHE["gen"] = None, _CACHE["gen"] + 1  # show the new pack right away; a list read before the save is not kept
    return out


_CACHE: dict = {"at": 0.0, "v": None, "gen": 0}  # the list is cached briefly so the summary page does not wait on storage every view
NAME = re.compile(r"^[0-9TZ-]+-[0-9a-f]{8}\.zip$")


def saved(limit: int = 5) -> dict:
    """Packs already in the vault, newest first (names and sizes, no links). Never raises."""
    c = vault_s3.conf()
    if not c:
        return {"on": False, "packs": [], "error": ""}
    if _CACHE["v"] and time.time() - _CACHE["at"] < 30:
        return _CACHE["v"]
    gen = _CACHE["gen"]
    try:
        rows = vault_s3.list_keys(c, PREFIX)[:limit]
        v = {"on": True, "error": "", "packs": [{"name": k[len(PREFIX):], "kb": max(1, size // 1024), "at": at[:16].replace("T", " ")}
                                                 for k, size, at in rows]}
    except Exception as e:  # storage down or a bad answer: the summary page still opens (and does not retry on every view)
        v = {"on": True, "packs": [], "error": f"Could not list the saved proof: {str(e)[:160]}"}
    if gen == _CACHE["gen"]:
        _CACHE.update(at=time.time(), v=v)
    return v


def link(name: str, who: str) -> str:
    """A 5-minute signed download link for one saved pack (the route checks Maria's PIN first). The download is chained."""
    c = vault_s3.conf()
    if not c:
        raise vault_s3.VaultError("Vultr Object Storage is not set up on this server")
    if not NAME.match(name) or not vault_s3.exists(c, PREFIX + name):
        raise ValueError("no such proof file")
    with state.LOCK:
        state.log("evidence_downloaded", {"key": PREFIX + name, "by": who})
    return vault_s3.signed_url(c, PREFIX + name, 300)
