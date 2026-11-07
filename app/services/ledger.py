# app/services/ledger.py — chain verify and the tamper demo (deep copy; the real chain is never touched).
import copy

from app import state
from core import chain


def verify() -> dict:
    with state.LOCK:
        return chain.verify(state.CHAIN)


def head() -> str | None:
    """Latest entry hash, shown next to a verify result so a viewer can note it and compare later."""
    with state.LOCK:
        return state.CHAIN[-1]["hash"] if state.CHAIN else None


def tamper_demo(seq: int | None = None) -> dict:
    """Flip one character inside one entry's payload of a COPY and verify the copy."""
    with state.LOCK:
        forged = copy.deepcopy(state.CHAIN)
    if not forged:
        return {"ok": None, "length": 0, "first_bad_seq": None, "tampered_seq": None, "note": "chain is empty"}
    seq = seq if seq and 1 <= seq <= len(forged) else (len(forged) + 1) // 2
    e = forged[seq - 1]
    texts = [k for k, v in sorted(e["payload"].items()) if isinstance(v, str) and v]
    field = "amount" if "amount" in texts else next(iter(texts), None)  # a changed amount reads best on screen
    if field is None:
        return {"ok": None, "length": len(forged), "first_bad_seq": None, "tampered_seq": seq, "note": "no text field"}
    v = e["payload"][field]
    e["payload"][field] = v[:-1] + ("1" if v[-1] != "1" else "2")  # one character changed
    res = chain.verify(forged)
    return {**res, "tampered_seq": seq, "field": field, "before": v, "after": e["payload"][field],
            "note": "a copy was tampered; the real chain is unchanged"}
