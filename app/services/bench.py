# app/services/bench.py — read-only view of bench/results/*.json and bench/baseline.md (never written here).
import json
import logging

from app import config

log = logging.getLogger(__name__)
RESULTS = config.ROOT / "bench" / "results"
BASELINE = config.ROOT / "bench" / "baseline.md"


def load(name: str = "latest") -> dict | None:
    """None (and a logged error) if the bench file is missing or unreadable; pages then say 'no bench results'."""
    p = RESULTS / f"{name}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.error("cannot read %s: %s", p, e)
        return None


def baseline() -> dict:
    """Human baseline stays 'to be measured' until someone replaces the placeholder in bench/baseline.md."""
    try:
        text = BASELINE.read_text(encoding="utf-8")
    except OSError:
        return {"measured": False, "text": "to be measured"}
    if "not yet measured" in text:
        return {"measured": False, "text": "to be measured (stopwatch, bench/baseline.md)"}
    lines = [l.strip("- ").strip() for l in text.splitlines() if l.lstrip().startswith("- ")]
    return {"measured": True, "text": "; ".join(lines) or "see bench/baseline.md"}



def extra(rel: str) -> dict | None:
    """Another bench JSON by repo-relative path (blind set B, second-model check); None if missing. Read-only."""
    p = config.ROOT / rel
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.error("cannot read %s: %s", p, e)
        return None


def measured() -> dict:
    """Everything the 'measured' panel shows, wins and losses, from result files only."""
    return {"b": load("latest"), "base": baseline(), "hb": extra("bench/heldout/set_b/results.json"),
            "xc": extra("bench/xcheck/results.json")}
