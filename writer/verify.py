# writer/verify.py — second path: re-reads a run as read-only cg_reader, recomputes row hashes, compares with the writer receipt.
import os

import psycopg
from psycopg.rows import dict_row

from writer.db import COLS, row_hash


def verify_run(run_id: str, receipt: dict, dsn: str | None = None) -> dict:
    """{reader_count, writer_count, match}. match needs equal counts, every stored hash recomputing, and same hash set."""
    with psycopg.connect(dsn or os.environ["CG_READER_DSN"], row_factory=dict_row) as c:
        c.read_only = True
        rows = c.execute(f"SELECT {', '.join(COLS)}, row_hash FROM journal_entries WHERE run_id = %s",
                         (run_id,)).fetchall()
    recomputed = [row_hash(r) for r in rows]
    intact = all(h == r["row_hash"].strip() for h, r in zip(recomputed, rows))
    match = (len(rows) == receipt["written"] and intact
             and sorted(recomputed) == sorted(receipt["hashes"]))
    return {"reader_count": len(rows), "writer_count": receipt["written"], "match": match}
