# app/routes/ledger_export.py — GET /ledger.jsonl: the audit chain as NDJSON, byte-for-byte what /ledger/verify checks.
from fastapi import APIRouter, Response

from app import state
from core import chain

router = APIRouter()


@router.get("/ledger.jsonl")
def export():
    """One canonical JSON entry per line (seq, prev_hash, kind, at, payload, hash); the chain holds no secrets."""
    with state.LOCK:
        body = "".join(chain.canonical(e) + "\n" for e in state.CHAIN)
    return Response(body, media_type="application/x-ndjson",
                    headers={"Content-Disposition": 'attachment; filename="closeguard-ledger.jsonl"'})
