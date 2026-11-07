# app/services/voice.py — answers a confirmed question from run state with templates (no LLM); audio cache, rate bucket, chain.
import hashlib
import os
import threading
import time
from collections import deque

from agent import voice as av
from app import config, state
from app.services import desk, plain, runs, scene

PENDING: dict = {}  # audio key -> answer text, so the audio route can synthesise lazily (answers are server-made)
_HITS: deque = deque()
_LOCK = threading.Lock()
DEMO_DIR = config.ROOT / "app" / "static" / "voice"
VAR_DIR = config.ROOT / "var" / "voice_cache"


def per_hour() -> int:
    try:
        return int(os.environ.get("CG_VOICE_LIVE_PER_HOUR", "60"))
    except ValueError:
        return 60


def take() -> bool:
    """One live STT/TTS call from the hourly bucket; False = used up (cache hits never call this)."""
    with _LOCK:
        now = time.monotonic()
        while _HITS and now - _HITS[0] > 3600:
            _HITS.popleft()
        if len(_HITS) >= per_hour():
            return False
        _HITS.append(now)
        return True


def audio_key(text: str) -> str:
    return hashlib.sha256(f"{av.TTS_MODEL}|{text}".encode()).hexdigest()[:32]  # new voice = new audio, never a stale one


def find_audio(key: str):
    for d in (DEMO_DIR, VAR_DIR):
        for p in d.glob(f"{key}.*") if d.is_dir() else ():
            return p
    return None


money = plain.money


def _why(run, line):
    if line not in run.bank:
        return "Tell me which bank line, for example B0078, and I will say why it was held or passed."
    d, b = run.decisions[line], run.bank[line]
    inv = next((", ".join(r["p"].inv_ids) for r in runs.rows(run) if r["p"].txn_id == line), "") or "no invoice"
    if d.result == "allow":
        done = "posted" if line in run.posted else "approved" if any(a.txn_id == line for a in run.approvals) else "waiting for a named human to approve it"
        return f"Bank line {line}, {money(b.amount)}, passed every check against {inv}. It is {done}."
    return f"Bank line {line}, {money(b.amount)}, is on hold. {plain.reason(d.rule, d.detail)} Nobody can approve it, so nothing was posted."


def _todo(run):
    ids = [t for t, d in run.decisions.items() if d.result == "allow" and t not in {a.txn_id for a in run.approvals}]
    if not ids:
        return "Nothing is left to approve."
    flagged = sum(bool(run.decisions[t].flag) for t in ids)
    first = ", ".join(f"{t} for {money(run.bank[t].amount)}" for t in ids[:3])
    extra = f" {flagged} have a flagged memo the approver must read first." if flagged else ""
    return f"{len(ids)} lines passed every check and are waiting for a person to approve them. First: {first}.{extra}"


def _summary(run, sc):
    top = ", ".join(f"{r} ({n})" for r, n in sc["rules"][:3])
    c = run.counters()
    return (f"{c['bank lines']} bank lines. {c['allowed']} passed every check, {c['refused']} are on hold" + (f". Main reasons: {top}" if top else "")
            + f". {c['approved']} approved, {c['posted']} posted" + (", and every posted entry was double-checked." if sc["verified"] else "."))


def _bill(bill, why):
    if not bill:
        return "No bill is on the desk yet. Scan one first."
    return desk.bill_answer(bill, why)


def answer(run, text: str, heard: str | None = None, bill: dict | None = None) -> dict:
    """text = what the user confirmed. Returns intent, line, answer, form (approve pre-fill only), note. Chains one voice_query."""
    text = text.strip()[:300]
    fixed, note = av.normalise_ids(text, run.bank)
    it = av.parse(fixed, bill=bool(bill))
    sc = scene.summary(run, runs.rows(run))
    form = None
    if it.name == "why":
        out = _why(run, it.line)
    elif it.name == "todo":
        out = _todo(run)
    elif it.name == "summary":
        out = _summary(run, sc)
    elif it.name == "approve":
        form = {"name": it.who, "role": it.role}
        who = ", ".join(x for x in (it.who, it.role) if x)
        out = f"Form filled{' for ' + who if who else ''}. Click Approve to confirm; nothing is approved until a named human clicks."
    elif it.name in ("bill_why", "bill_read"):
        out = _bill(bill, it.name == "bill_why")
    else:
        out = "I can answer: why a line is on hold, what is left to approve, or the close summary."
    out = f"{note} {out}" if note else out
    with state.LOCK:
        state.log("voice_query", {"run_id": run.id, "text": text, "heard": heard, "intent": it.name, "line": it.line,
                                  "answer": out, "stt_model": av.STT_MODEL if heard is not None else None, "tts": av.TTS_MODEL})
    key = audio_key(out)
    PENDING[key] = out
    while len(PENDING) > 200:
        PENDING.pop(next(iter(PENDING)))
    return {"intent": it.name, "line": it.line, "answer": out, "form": form, "key": key,
            "has_audio": bool(find_audio(key)) or config.model_live()}  # else: browser voice, no 404 request


def audio(key: str):
    """Path of the audio for `key`: committed demo, cache, or one live TTS call if switched on and within budget."""
    if (p := find_audio(key)) or key not in PENDING or not config.model_live() or not take():
        return p
    data = av.speak(PENDING[key], "wav")
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    p = VAR_DIR / f"{key}.wav"
    p.write_bytes(data)
    return p
