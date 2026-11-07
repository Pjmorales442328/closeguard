# agent/seed_bills.py — reads the committed demo bills with both models and fills agent/cache_intake (24 calls first time).
# Run: CG_ENV_FILE=<path to .env> python -m agent.seed_bills   (the key is loaded by code, never printed)
import json
import os
import sys
from pathlib import Path

from agent import extract

BILLS = Path(__file__).resolve().parent.parent / "data" / "synthetic" / "bills"


def main() -> int:
    if os.environ.get("CG_ENV_FILE"):
        extract.load_key_from(os.environ["CG_ENV_FILE"])
    os.environ["CG_MODEL_LIVE"] = "1"
    cached = live = bad = 0
    for m in json.loads((BILLS / "manifest.json").read_text("utf-8"))["bills"]:
        for raw, meta in extract.two_readings((BILLS / m["file"]).read_bytes(), "image/jpeg"):
            if raw is None:
                bad += 1
                print(m["file"], "FAILED", meta.get("model"), meta.get("error"))
            elif meta.get("cached"):
                cached += 1
            else:
                live += 1
    print(f"{cached + live + bad} readings: {cached} cached, {live} live, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
