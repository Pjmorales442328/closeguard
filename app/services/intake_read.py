# app/services/intake_read.py — one bill card: both models read it, stdlib checks run, status is decided and chained.
from dataclasses import dataclass, field

from agent import extract
from app import state
from core.intake_checks import FIELDS, IntakeError, agree, check, failed, normalise, ref_key
from core.intake_merge import show
from data.world import VENDORS


@dataclass
class Card:
    n: int
    name: str
    mime: str
    data: bytes
    sha: str
    bill_id: str = ""  # chain id "<batch>/<nn>"
    status: str = "received"  # received | ready | confirm | refused | unreadable | confirmed | rejected
    readings: list = field(default_factory=lambda: [None, None])  # Bill or None per model, in extract.MODELS order
    metas: list = field(default_factory=lambda: [{}, {}])
    errors: list = field(default_factory=lambda: ["", ""])
    diffs: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)  # reading index -> [Decision]
    passing: list = field(default_factory=list)  # reading indexes whose checks all pass
    chosen: int | None = None  # reading index when both readers agreed
    merged: object = None  # Bill built from the human's per-field picks (or the one readable reading)
    sources: dict = field(default_factory=dict)  # field -> reader model name or "typed"
    by: str = ""
    notice: str = ""  # last refusal shown on the card (SoD, failed recheck)


def final(card):
    """The bill that goes into the ledger: the human-merged one, else the agreed reading."""
    return card.merged or card.readings[card.chosen]


def pick_fields(card) -> list:
    """[(field, reader A value, reader B value)] for the fields the readers differ on (empty when only one reading exists)."""
    if not all(card.readings) or not card.diffs:
        return []
    return [(f, show(card.readings[0], f), show(card.readings[1], f)) for f in card.diffs]


def seen_refs(batch_cards, card) -> frozenset:
    """Invoice numbers already read on earlier bills of the same batch (first usable reading of each)."""
    out = set()
    for c in batch_cards:
        if c.n >= card.n:
            break
        r = next((b for b in c.readings if b), None)
        if r:
            out.add(ref_key(r.invoice_no))
    return frozenset(out)


def decide(card, refs) -> None:
    have = [i for i in (0, 1) if card.readings[i]]
    card.checks = {i: check(card.readings[i], refs, VENDORS, card.bill_id) for i in have}
    card.passing = [i for i in have if not failed(card.checks[i])]
    card.diffs = agree(*card.readings) if len(have) == 2 else (["one reader unreadable"] if have else [])
    if not have:
        card.status = "unreadable"
    elif not card.passing:
        card.status = "refused"
    elif card.diffs:
        card.status = "confirm"
    else:
        card.status, card.chosen = "ready", card.passing[0]
    with state.LOCK:
        state.log("bill_checked", {"bill_id": card.bill_id, "diffs": card.diffs, "status": card.status,
                                   "checks": [{"reading": extract.MODELS[i], "rule": d.rule or "ok", "result": d.result,
                                               "detail": d.detail} for i in have for d in card.checks[i]]})


def read_card(card, refs, live: bool = False, on_read=None) -> None:
    extra = {"live": live, "on_read": on_read} if live or on_read else {}  # plain calls keep the old signature
    for i, (raw, meta) in enumerate(extract.two_readings(card.data, card.mime, **extra)):
        card.metas[i] = meta
        if raw is None:
            card.errors[i] = meta.get("error", "unreadable")
        else:
            try:
                card.readings[i] = normalise(raw)
            except IntakeError as e:  # off-schema answer = unreadable, never a partial bill
                card.errors[i] = f"off-schema answer: {e}"
        b = card.readings[i]
        with state.LOCK:
            state.log("bill_read", {"bill_id": card.bill_id, "model": extract.MODELS[i], "latency_s": meta.get("latency_s"),
                                    "cached": meta.get("cached"), "vultr": meta.get("vultr"),
                                    "fields": {f: str(getattr(b, f)) for f in FIELDS} if b else "unreadable"})
    decide(card, refs)
