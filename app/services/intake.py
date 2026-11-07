# app/services/intake.py — bill batches in memory: validate uploads, read, human confirm/reject, then hand rows to the close run.
import hashlib
import json
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass

from app import config, state
from app.services import intake_read as ir
from app.services import runs
from core.csvload import load_bank
from core.intake_checks import to_ledger_line
from data.world import GL, VENDORS

MAX_FILES, MAX_BYTES, MAX_HELD = 10, 4 * 1024 * 1024, 20
MAGIC = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg"}  # decided by bytes, never by file name
BILLS_DIR = config.DATA / "bills"
BATCHES: OrderedDict = OrderedDict()
_demo_lock = threading.Lock()


class IntakeRefused(ValueError):
    """Upload rejected before anything is read: wrong type, too big, too many."""


@dataclass
class Batch:
    id: str
    cards: list
    uploaded: bool  # True = visitor images (memory only, run is the unlisted uploaded kind)
    thread: threading.Thread | None = None

    def pending(self) -> bool:
        return any(c.status == "received" for c in self.cards)


def _mime(data: bytes) -> str:
    return next((m for k, m in MAGIC.items() if data.startswith(k)), "")


def _make(bid: str, files: list, uploaded: bool) -> Batch:
    cards = []
    for n, (name, data) in enumerate(files, 1):
        c = ir.Card(n, name[:60], _mime(data), data, hashlib.sha256(data).hexdigest(), f"{bid}/{n:02d}")
        cards.append(c)
        with state.LOCK:
            state.log("bill_received", {"bill_id": c.bill_id, "sha256": c.sha, "bytes": len(data), "mime": c.mime, "name": c.name})
    return Batch(bid, cards, uploaded)


def receive(files: list) -> Batch:
    """files = [(name, bytes)]. Raises IntakeRefused. Visitor images are never written to disk."""
    if not files or len(files) > MAX_FILES:
        raise IntakeRefused(f"choose 1 to {MAX_FILES} images")
    for name, data in files:
        if len(data) > MAX_BYTES:
            raise IntakeRefused(f"{name[:40]}: larger than {MAX_BYTES // (1024 * 1024)} MB")
        if not _mime(data):
            raise IntakeRefused(f"{name[:40]}: only PNG or JPEG images are accepted")
    b = _make(uuid.uuid4().hex[:12], files, True)
    with state.LOCK:
        BATCHES[b.id] = b
        while sum(len(x.cards) for x in BATCHES.values() if x.id != "demo") > MAX_HELD:  # oldest visitor batch goes first
            BATCHES.pop(next(k for k in BATCHES if k != "demo"))
    return b


def read_all(b: Batch) -> None:
    for c in b.cards:
        ir.read_card(c, ir.seen_refs(b.cards, c))


def start_reading(b: Batch) -> None:
    b.thread = threading.Thread(target=read_all, args=(b,), daemon=True)
    b.thread.start()


def demo() -> Batch:
    """The committed synthetic bills, read once from the committed cache (no network when the cache is complete)."""
    with _demo_lock:
        if "demo" not in BATCHES:
            names = [m["file"] for m in json.loads((BILLS_DIR / "manifest.json").read_text("utf-8"))["bills"]]
            b = _make("demo", [(n, (BILLS_DIR / n).read_bytes()) for n in names], False)
            read_all(b)
            BATCHES["demo"] = b
        return BATCHES["demo"]


def reset_demo() -> None:
    """Fresh demo batch (confirmations undone) so every presenter/judge can show the confirm step; the chain keeps history."""
    with _demo_lock:
        BATCHES.pop("demo", None)


def get(bid: str):
    return demo() if bid == "demo" else BATCHES.get(bid)


def make_run(b: Batch, bank=None):
    rows = [to_ledger_line(ir.final(c), c.n, VENDORS, GL) for c in b.cards if c.status in ("ready", "confirmed")]
    if not rows:
        raise IntakeRefused("no bill is ready or confirmed yet")
    run = runs.create_run(bank or load_bank(config.BILLS_BANK_CSV), rows, uploaded=b.uploaded, standin=False)
    with state.LOCK:
        run.source += f" | ledger from {len(rows)} bill images"
        state.log("intake_run", {"run_id": run.id, "bill_ids": [c.bill_id for c in b.cards if c.status in ("ready", "confirmed")],
                                 "inv_ids": [r.inv_id for r in rows]})
    return run
