# app/services/signin.py — Maria's PIN for the money steps (approve, QuickBooks export). Checked on the server, wrong tries lock it, every refusal is chained.
import hmac
import os
import time

from app import state

TRIES, LOCK_S = 5, 60
_fails: dict = {}  # who -> (wrong tries in a row, locked until)


def demo_pin() -> str:
    return os.environ.get("CG_MARIA_PIN") or "2468"  # one demo approver; a real login (and hashed PINs) replaces this


def check(who: str, pin: str, what: str) -> str | None:
    """None when the PIN is right; otherwise the plain reason to show. Never says which digit was wrong."""
    n, until = _fails.get(who, (0, 0))
    if until > time.time():
        return f"Too many wrong PINs. Locked for {int(until - time.time()) + 1} more seconds."
    if hmac.compare_digest(str(pin or "").strip().encode(), demo_pin().encode()):
        _fails.pop(who, None)
        return None
    n += 1
    _fails[who] = (0, time.time() + LOCK_S) if n >= TRIES else (n, 0)
    with state.LOCK:
        state.log("pin_refused", {"who": who, "what": what, "tries": n, "locked": n >= TRIES})
    return "Wrong PIN. Nothing was approved or exported." + (" Locked for a minute after 5 tries." if n >= TRIES else f" {TRIES - n} tries left.")
