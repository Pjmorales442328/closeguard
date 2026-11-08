# app/services/signin.py — Maria's PIN for the money steps (approve, QuickBooks export). Checked on the server, wrong tries lock it, every refusal is chained.
# She can let this browser remember it for an hour: a signed, HttpOnly cookie the server checks on every money step.
import hashlib
import hmac
import os
import secrets
import time

from app import state

TRIES, LOCK_S = 5, 60
COOKIE, HOLD_S = "cg_pin", 3600
_SECRET = (os.environ.get("CG_SESSION_SECRET") or secrets.token_hex(32)).encode()  # per process if unset: a restart forgets everyone
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


def _sig(who: str, until: int) -> str:
    return hmac.new(_SECRET, f"{who}|{until}|{demo_pin()}".encode(), hashlib.sha256).hexdigest()  # a PIN change ends every remembered browser


def remembered(request, who: str) -> int:
    """Until when (unix seconds) this browser may act as `who` without typing the PIN; 0 = not remembered."""
    try:
        w, until, sig = request.cookies.get(COOKIE, "").split("|")
        ok = w == who and int(until) > time.time() and hmac.compare_digest(sig, _sig(w, int(until)))
        return int(until) if ok else 0
    except (ValueError, TypeError):  # missing, malformed or non-ASCII cookie: not remembered
        return 0


def _pin(form) -> str:
    return str(form.get("pin") or "").strip()[:64]


def gate(request, form, who: str, what: str) -> str | None:
    """The PIN if one was typed, else the remembered browser. An empty PIN never counts as a wrong try."""
    pin = _pin(form)
    if not pin:
        if _fails.get(who, (0, 0))[1] > time.time():  # the wrong-PIN lock covers remembered browsers too
            return check(who, "", what)
        return None if remembered(request, who) else f"Enter {who}'s PIN."
    return check(who, pin, what)


def keep(resp, request, form, who: str):
    """After a correct PIN with "remember" ticked: this browser skips the PIN for an hour. Chained."""
    if form.get("remember") == "yes" and _pin(form):
        until = int(time.time()) + HOLD_S
        resp.set_cookie(COOKIE, f"{who}|{until}|{_sig(who, until)}", max_age=HOLD_S, httponly=True, samesite="strict",
                        secure=request.headers.get("x-forwarded-proto", request.url.scheme) == "https")
        with state.LOCK:
            state.log("pin_remembered", {"who": who, "for_s": HOLD_S})
    return resp


def forget(resp, who: str = "Maria"):
    resp.delete_cookie(COOKIE)
    with state.LOCK:
        state.log("pin_forgotten", {"who": who})
    return resp
