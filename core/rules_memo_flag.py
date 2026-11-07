# core/rules_memo_flag.py — SOFT tier: finance/approval vocabulary in a memo never refuses; it flags the proposal so the
# human approver must acknowledge the text before approving (core.sod.check_approval, policy.memo_unacknowledged).
import re

from core.rules_memo_text import normalise

SOFT = re.compile(
    r"\b(approv\w*|authori[sz]\w*|pre-?(cleared|validated|verified)|partial(ly)? (payment|paid)|short[- ]?pa\w+|discount\w*"
    r"|credit (note|memo)|settles?|settled|cfo|controller|auditor|finance director|ceo|board resolution|per contract"
    r"|per policy|overrid\w*|ignore|disregard|bypass|exempt|verified|signed[- ]off|signed:|trusted|whitelist\w*"
    r"|release (the )?funds|no exceptions|dual approval|reviewer|sign-?off|escalat\w*|precomputed|not applicable"
    r"|cap|caps|threshold|limit|suspense|round (up|down|to)|times the|amount (due )?is|actually|instead|correct(ed)? gl"
    r"|gl is|bank details|iban|bank accounts?|delete|create a payment|second entry|crediting|debiting|repeat|trust me"
    r"|just this once|test transaction|intercompany|in thousands|multiply|if you|rest later|in (eur|usd|gbp|php|jpy)"
    r"|aprobar|aprueb\w*|aprov\w*|aprubahan|approuver|validez|genehmig\w*|buche\w*|freigabe)\b"
    r"|批准|承認|승인|[оo]д[оo]б[рp]\w*|وافق|स्वीकृत|balance\s*=", re.I)


def find(text: str):
    """The first finance/approval term in the folded text, else None."""
    m = SOFT.search(normalise(text or ""))
    return m.group(0) if m else None


def memo_flag(p, c):
    """Soft flag for an otherwise allowed proposal: 'memo: term' / 'reference: term', else None."""
    b = c.bank[p.txn_id]
    for field in ("memo", "reference"):
        term = find(getattr(b, field))
        if term:
            return f"{field}: {term!r}"
