# app/config.py — reads env once: DB DSNs (absent = demo store), live-model switch, data dir.
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "synthetic"
BANK_CSV = DATA / "bank_2026-10.csv"
BILLS_BANK_CSV = DATA / "bank_bills_2026-10.csv"  # bills-sized default for "Run the close with these bills" (data/bills_bank_gen.py)
LEDGER_CSV = DATA / "ledger_2026-10.csv"
FAULTS = DATA / "faults.json"


def writer_dsn():
    return os.environ.get("CG_WRITER_DSN") or None


def reader_dsn():
    return os.environ.get("CG_READER_DSN") or None


def model_live() -> bool:
    """Live model calls only when explicitly switched on; default is the offline deterministic proposer."""
    return os.environ.get("CG_MODEL_LIVE", "").strip() == "1"


def attempts_path() -> Path:
    """JSONL of try-to-trick attempts (public counter). Override with CG_ATTEMPTS; folder var/ is gitignored."""
    return Path(os.environ.get("CG_ATTEMPTS") or ROOT / "var" / "attempts.jsonl")


def runtime_cache() -> Path:
    """Where live-run answers are saved: never the committed agent/cache/. Override with CG_RUNTIME_CACHE."""
    return Path(os.environ.get("CG_RUNTIME_CACHE") or ROOT / "var" / "model_cache")
