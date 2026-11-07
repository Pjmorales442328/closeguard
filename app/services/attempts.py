# app/services/attempts.py — append-only JSONL of try-to-trick attempts and the public counter computed from it.
import json
import logging
import threading

from app import config

_LOCK = threading.Lock()
log = logging.getLogger(__name__)


def record(a: dict) -> None:
    """Append one attempt. A write failure is logged, never hidden as a fake count."""
    line = json.dumps(a, ensure_ascii=True, default=str)
    p = config.attempts_path()
    with _LOCK:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8", newline="\n") as f:
                f.write(line + "\n")
        except OSError as e:
            log.error("could not persist trick attempt to %s: %s", p, e)


def _load() -> list:
    p = config.attempts_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            log.warning("skipping malformed line in %s", p)
    return out


def counter() -> dict:
    """Every number is counted from stored outcomes, including the 'posted without approval' zero."""
    rows = _load()
    return {"attempts": len(rows),
            "blocked": sum(r.get("gate") == "refuse" for r in rows),
            "flagged": sum(r.get("gate") == "allow" and bool(r.get("flag")) for r in rows),
            "passed_gate": sum(r.get("gate") == "allow" and not r.get("flag") for r in rows),
            "posted_without_approval": sum(r.get("post_without_approval") == "allow" for r in rows)}
