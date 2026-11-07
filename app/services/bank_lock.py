# app/services/bank_lock.py — a supplier that asks to change bank details is locked: no payment to it can be approved until Maria calls back.
# The classic invoice scam is "our bank details have changed". A fixed rule, not the model, holds the money; the call-back is chained.
import threading
import time

from app import state

LOCKS: dict = {}  # supplier name (upper) -> {"supplier", "since", "thread", "cleared_by", "cleared_at"}
_lock = threading.Lock()
RULE = "policy.supplier_locked"


def _k(name) -> str:
    return " ".join(str(name or "").split()).upper()


def lock(supplier: str, thread: str) -> None:
    """Called when a reply asks to pay a different account. A second scam reply re-locks even after a call-back."""
    with _lock:
        LOCKS[_k(supplier)] = {"supplier": supplier, "since": time.time(), "thread": thread, "cleared_by": None, "cleared_at": None}
    with state.LOCK:
        state.log("supplier_locked", {"supplier": supplier, "thread": thread, "why": "reply asks to pay a different bank account"})


def locked(supplier) -> bool:
    with _lock:
        x = LOCKS.get(_k(supplier))
        return bool(x and not x["cleared_by"])


def status(supplier) -> str:
    """'locked', 'called_back' (Maria lifted it) or '' (never locked, or the lock was lost with a restart)."""
    with _lock:
        x = LOCKS.get(_k(supplier))
        return "" if not x else "called_back" if x["cleared_by"] else "locked"


def held() -> list:
    """Suppliers still locked, oldest first (for the pay screen)."""
    with _lock:
        return sorted((x["supplier"] for x in LOCKS.values() if not x["cleared_by"]), key=lambda s: LOCKS[_k(s)]["since"])


def call_back(supplier: str, who: str) -> bool:
    """Maria called the supplier on the number already on file (never the one in the email): bank details unchanged, lock lifted.
    The PIN is checked by the route before this. False when the supplier was not locked."""
    with _lock:
        x = LOCKS.get(_k(supplier))
        if not x or x["cleared_by"]:
            return False
        x["cleared_by"], x["cleared_at"] = who, time.time()
    with state.LOCK:
        state.log("supplier_called_back", {"supplier": x["supplier"], "by": who, "result": "bank details unchanged, lock lifted"})
    return True


def clear() -> None:
    with _lock:
        LOCKS.clear()
