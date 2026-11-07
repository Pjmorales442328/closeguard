# app/services/proposals.py — the ONE seam to the model: agent.propose if switched on, else faults.json baits.
import json
import threading
import time
from decimal import Decimal

from app import config
from app.services.recorder import BUDGET_NOTE, Recorder
from core.models import Proposal

COOLDOWN_S = 60  # public site: at most one live run per minute, globally
_LAST_LIVE = [0.0]
_LOCK = threading.Lock()


def _fallback(proposals: list) -> list:
    """Deterministic stand-in for the model: the planted bait proposals from faults.json on unmatched lines."""
    faults = json.loads(config.FAULTS.read_text(encoding="utf-8"))["faults"]
    baits = {f["txn_id"]: f["bait"] for f in faults if f["bait"]}
    out = []
    for p in proposals:
        bait = baits.get(p.txn_id) if p.kind == "unmatched" else None
        if bait:
            inv, amt = tuple(bait["inv_ids"]), Decimal(bait["amount"])
            p = Proposal(p.txn_id, inv, amt, dict.fromkeys(inv, amt), "match", "model stand-in (offline bait)")
        out.append(p)
    return out


def _claim_live() -> bool:
    with _LOCK:
        now = time.monotonic()
        if _LAST_LIVE[0] and now - _LAST_LIVE[0] < COOLDOWN_S:
            return False
        _LAST_LIVE[0] = now
        return True


def get_proposals(unmatched_and_matched: list, bank: list, ledger: list, live: bool = False, standin: bool = True) -> tuple:
    """(proposals, source, meta). Model only with CG_MODEL_LIVE=1; live=True skips the cache read; any failure falls back.
    meta = {"mode": live|cache|offline, "calls": [{txn, how, latency_s, tokens, error}], "note": str}."""
    if not config.model_live():
        note = "live AI calls are switched off on this server" if live else ""
        meta = {"mode": "offline", "calls": [], "note": note}
        if not standin:  # bills runs: no planted baits, lines without a model answer stay unmatched
            meta["note"] = "AI is off: lines the exact-match rules could not pair stay unmatched"
            return unmatched_and_matched, "deterministic matcher only (model off; no stand-in baits)", meta
        return _fallback(unmatched_and_matched), "deterministic fallback (offline, faults.json baits)", meta
    note = ""
    if live and not _claim_live():
        live, note = False, f"live AI is resting (one live run per {COOLDOWN_S} s), saved answers used"
    rec = None
    try:
        from agent.propose import propose
        rec = Recorder(live)
        out = propose(unmatched_and_matched, bank, ledger, rec)
    except Exception as e:  # noqa: BLE001 — never block a run on the model; say so on screen
        meta = {"mode": "offline", "calls": rec.calls if rec else [], "note": f"AI failed ({type(e).__name__}), the practice stand-in was used"}
        if not standin:
            return unmatched_and_matched, f"deterministic matcher only (model failed: {type(e).__name__})", meta
        return _fallback(unmatched_and_matched), f"deterministic fallback (model failed: {type(e).__name__})", meta
    fb, lost, skip = ([c["txn"] for c in rec.calls if c["how"] == k] for k in ("fallback", "failed", "skipped"))
    note = "; ".join(filter(None, [note, fb and f"live AI call failed for {', '.join(fb)}, saved answer used",
                                   lost and f"no AI answer for {', '.join(lost)}, left unmatched",
                                   skip and f"{BUDGET_NOTE}: {', '.join(skip)} not asked, left unmatched"]))
    meta = {"mode": "live" if live else "cache", "calls": rec.calls, "note": note}
    hits, n_live = (sum(c["how"] == k for c in rec.calls) for k in ("cached", "live"))
    how = "live, cache skipped" if live else "replayed from cache" if hits == len(rec.calls) else f"{n_live} live calls, {hits} cached"
    return out, f"model glm-5.3-flash (Vultr Serverless Inference, {how})" + (f"; {note}" if note else ""), meta


def model_mode() -> str:
    return "model (cache first, then live)" if config.model_live() else "offline fallback (faults.json baits)"


def cross_check(decisions: dict, proposals: list, bank: dict, ledger: dict) -> dict:
    """Second model (agent.xcheck) reviews gate-allowed model matches; disagreement becomes an amber flag to acknowledge.
    Only with CG_MODEL_LIVE=1 (cache first); any failure is itself flagged inside agent.xcheck, never silent."""
    if not config.model_live():
        return decisions
    from agent.xcheck import flag_decisions
    return flag_decisions(decisions, proposals, bank, ledger)
