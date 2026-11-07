# core/csvload.py — strict CSV -> dataclass parsing for bank and ledger files (stdlib, Decimal only, 2 MB cap).
import csv
from datetime import date
from pathlib import Path

from core.models import BankLine, LedgerLine, money

MAX_BYTES = 2 * 1024 * 1024
BANK_COLS = ("txn_id", "date", "amount", "direction", "counterparty", "reference", "memo")
LEDGER_COLS = ("inv_id", "vendor", "vendor_known", "inv_date", "due_date", "amount", "reference", "gl_account")


class CsvError(ValueError):
    """Any reason the file cannot be trusted: size, columns, empty fields, bad values, duplicate ids."""


def _rows(text: str, cols, label: str, optional=()):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise CsvError(f"{label}: file exceeds {MAX_BYTES} bytes")
    lines = [l for l in text.splitlines() if not l.startswith("#")]  # '# SYNTHETIC' banner lines
    reader = csv.DictReader(lines)
    missing = [c for c in cols if c not in (reader.fieldnames or [])]
    if missing:
        raise CsvError(f"{label}: missing columns {missing}")
    for n, row in enumerate(reader, start=2):
        for c in cols:
            if c in optional:
                continue
            if row.get(c) is None or not row[c].strip():
                raise CsvError(f"{label} row {n}: empty required field {c!r}")
        yield n, row


def _date(s: str, label: str, n: int) -> date:
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        raise CsvError(f"{label} row {n}: bad date {s!r}") from None


def _money(s: str, label: str, n: int):
    try:
        return money(s)
    except (ValueError, TypeError) as e:
        raise CsvError(f"{label} row {n}: {e}") from None


def _unique(ids, label):
    seen = set()
    for i in ids:
        if i in seen:
            raise CsvError(f"{label}: duplicate id {i!r}")
        seen.add(i)


def parse_bank(text: str) -> list:
    out = []
    for n, r in _rows(text, BANK_COLS, "bank", optional=("memo",)):
        direction = r["direction"].strip().upper()
        if direction not in ("DR", "CR"):
            raise CsvError(f"bank row {n}: direction must be DR or CR")
        out.append(BankLine(r["txn_id"].strip(), _date(r["date"], "bank", n), _money(r["amount"], "bank", n),
                            direction, r["counterparty"].strip(), r["reference"].strip(), (r.get("memo") or "").strip()))
    _unique((b.txn_id for b in out), "bank")
    return out


def parse_ledger(text: str) -> list:
    out = []
    for n, r in _rows(text, LEDGER_COLS, "ledger"):
        known = r["vendor_known"].strip().upper()
        if known not in ("Y", "N"):
            raise CsvError(f"ledger row {n}: vendor_known must be Y or N")
        out.append(LedgerLine(r["inv_id"].strip(), r["vendor"].strip(), known == "Y", _date(r["inv_date"], "ledger", n),
                              _date(r["due_date"], "ledger", n), _money(r["amount"], "ledger", n),
                              r["reference"].strip(), r["gl_account"].strip()))
    _unique((l.inv_id for l in out), "ledger")
    return out


def _read(path) -> str:
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise CsvError(f"{p.name}: file exceeds {MAX_BYTES} bytes")
    return p.read_text(encoding="utf-8")


def load_bank(path) -> list:
    return parse_bank(_read(path))


def load_ledger(path) -> list:
    return parse_ledger(_read(path))
