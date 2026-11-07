# app/services/books_export.py — posted entries as a journal CSV that QuickBooks Online (Import Data > Journal Entries) maps.
import csv
import io

from app.services.posting import AP_GL, BANK_GL

HEADER = ["Journal No", "Journal Date", "Account", "Debits", "Credits", "Description", "Name"]
ACCOUNTS = {AP_GL: f"{AP_GL} Accounts Payable", BANK_GL: f"{BANK_GL} Bank"}  # fixed names, map once in QBO


def rows(run) -> list:
    """Two balanced lines per posted invoice payment (Dr A/P, Cr Bank). Only posted entries, never proposals."""
    out = []
    for p in run.proposals:
        if p.txn_id not in run.posted:
            continue
        day = run.bank[p.txn_id].date.strftime("%m/%d/%Y")
        for inv, amt in p.parts.items():
            vendor = run.ledger[inv].vendor
            desc = f"Pay {inv} from bank {p.txn_id} ({'UPLOADED' if run.uploaded else 'SYNTHETIC'}, Closeguard run {run.id})"
            no = f"{p.txn_id}-{inv}"
            out.append([no, day, ACCOUNTS[AP_GL], f"{amt:.2f}", "", desc, vendor])
            out.append([no, day, ACCOUNTS[BANK_GL], "", f"{amt:.2f}", desc, vendor])
    return out


def csv_text(run) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEADER)
    w.writerows(rows(run))
    return buf.getvalue()
