# core/chain.py — SHA-256 hash-chained audit log: append-only entries; verify() reports the first tampered seq.
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True)


def _hash(prev: str, seq: int, kind: str, at: str, payload) -> str:
    body = canonical({"seq": seq, "kind": kind, "at": at, "payload": payload})
    return hashlib.sha256((prev + body).encode("utf-8")).hexdigest()


def append(entries: list, kind: str, payload, at: str | None = None) -> dict:
    prev = entries[-1]["hash"] if entries else GENESIS
    seq = len(entries) + 1
    at = at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    e = {"seq": seq, "prev_hash": prev, "kind": kind, "at": at, "payload": payload,
         "hash": _hash(prev, seq, kind, at, payload)}
    entries.append(e)
    return e


def verify(entries: list) -> dict:
    """{ok, length, first_bad_seq}. Any malformed entry counts as bad (fail closed)."""
    prev = GENESIS
    for i, e in enumerate(entries, 1):
        try:
            good = (e["seq"] == i and e["prev_hash"] == prev
                    and _hash(prev, i, e["kind"], e["at"], e["payload"]) == e["hash"])
        except (KeyError, TypeError):
            good = False
        if not good:
            return {"ok": False, "length": len(entries), "first_bad_seq": i}
        prev = e["hash"]
    return {"ok": True, "length": len(entries), "first_bad_seq": None}


def save(path, entries: list) -> None:
    Path(path).write_text("".join(canonical(e) + "\n" for e in entries), encoding="utf-8")


def load(path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
