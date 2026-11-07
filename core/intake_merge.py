# core/intake_merge.py — per-field resolution of two disagreeing bill readings; typed values go through the strict normaliser.
from core.intake_checks import FIELDS, Bill, IntakeError, normalise

SPLIT = ",+;"


def show(b: Bill, f: str) -> str:
    v = getattr(b, f)
    return " + ".join(str(x) for x in v) if f == "line_items" else str(v)


def _raw(b: Bill) -> dict:
    return {"supplier": b.supplier, "invoice_no": b.invoice_no, "invoice_date": b.invoice_date.isoformat(),
            "due_date": b.due_date.isoformat(), "currency": b.currency, "total": str(b.total),
            "line_items": [str(x) for x in b.line_items], "notes": b.notes}


def _typed(f: str, text: str):
    text = (text or "").strip()
    if f != "line_items":
        return text
    for ch in SPLIT[1:]:
        text = text.replace(ch, SPLIT[0])
    return [t.strip() for t in text.split(",") if t.strip()]


def merge(a: Bill, b: Bill, diffs: list, picks: dict) -> tuple:
    """picks: field -> '0' | '1' | 'other:<text>' for EVERY differing field. -> (merged Bill, {field: source}).
    Agreed fields stay as read. Raises IntakeError for a missing/unknown pick or a typed value the normaliser rejects."""
    raw, src = _raw(a), {}
    for f in diffs:
        if f not in FIELDS:
            raise IntakeError(f"cannot pick field {f!r}")
        p = (picks.get(f) or "").strip()
        if p in ("0", "1"):
            raw[f], src[f] = _raw((a, b)[int(p)])[f], ("reader A", "reader B")[int(p)]
        elif p.startswith("other:") and p[6:].strip():
            raw[f], src[f] = _typed(f, p[6:]), "typed"
        else:
            raise IntakeError(f"choose a value for {f}")
    return normalise(raw), src
