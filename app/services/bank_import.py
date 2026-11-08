# app/services/bank_import.py — the month's bank statement. On the demo server it is empty until Ana imports one (her bank's CSV or the sample); Clear forgets it.
import os

from app import config, state
from core.csvload import CsvError, load_bank, parse_bank

STATEMENT: dict = {"rows": None, "name": ""}
MAX_BYTES = 1_000_000


def _demo() -> bool:
    return os.environ.get("CG_SEED_DEMO") == "1"  # elsewhere (tests, local runs) the sample statement is simply there


def rows():
    """The statement's lines, or None when the demo month has no statement yet."""
    if STATEMENT["rows"] is not None:
        return STATEMENT["rows"]
    return None if _demo() else load_bank(config.BILLS_BANK_CSV)


def name() -> str:
    return STATEMENT["name"] or ("" if _demo() else "October statement (sample)")


def use(text: str, filename: str, who: str = "Ana (bookkeeper)") -> str | None:
    """None when imported, else the plain reason. Every bill already scanned is matched against it at once."""
    try:
        lines = parse_bank(text)
    except CsvError as e:
        return f"That file is not a bank statement this app can read: {e}"
    if not lines:
        return "That file has no payments in it."
    STATEMENT.update(rows=lines, name=filename)
    with state.LOCK:
        state.log("bank_imported", {"file": filename, "lines": len(lines), "by": who})
    from app.services import app_bank  # late import, app_bank reads rows()
    app_bank.rematch()
    return None


def sample() -> str | None:
    return use(config.BILLS_BANK_CSV.read_text("utf-8"), "October statement (sample)")


def clear() -> None:
    STATEMENT.update(rows=None, name="")
