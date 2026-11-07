# app/services/explain.py — picks the bank line the six numbered "follow one line" panels trace.
from app.services import plain
from app.services.scene import is_model


def _model(r) -> bool:
    return is_model(r["p"])


def pick(rows: list, line: str | None = None):
    """Requested line if it exists; else the most telling one: a model proposal the gate refused, then any refusal."""
    if not rows:
        return None
    by_id = {r["b"].txn_id: r for r in rows}
    if line and line in by_id:
        return by_id[line]
    refused = [r for r in rows if r["d"].result != "allow"]
    told = [r for r in refused if _model(r) and r["p"].inv_ids]  # the model really proposed a payment and was stopped
    return next(iter(told), None) or next((r for r in refused if _model(r)), None) or next(iter(refused), None) or rows[0]


def choices(rows: list) -> list:
    """Lines worth tracing, for the picker: refusals first (with rule), then flagged, then a few clean ones."""
    ref = [(r["b"].txn_id, f"held, {plain.short(r['d'].rule)}") for r in rows if r["d"].result != "allow"]
    flg = [(r["b"].txn_id, "allowed, flagged") for r in rows if r["d"].result == "allow" and r["d"].flag]
    ok = [(r["b"].txn_id, "allowed") for r in rows if r["d"].result == "allow" and not r["d"].flag]
    return ref + flg + ok
