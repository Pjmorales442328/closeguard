# app/services/events.py — the run's event feed, read only from the audit hash chain (no invented events).
"""Event dict schema (full reference: docs/plans/events-schema.md). Fields are only ever ADDED, never renamed.
Always: seq, seq_to, at, kind, hash (10 chars), tone, text, sub, short (<= 32 chars), rule, rule_label, txns, to, actor, n,
who, story, batch, items. `who` = matcher | model | stand-in | None; `story` = row holds a demo story line (UI pins
it); `batch` = row stands for n grouped matcher rows, whose single-line events are in `items` (chain order).
Kinds: run_created, gate_decision, approval, post, verify_db, xcheck_disagree (derived from a gate_decision flag)."""
from agent.xcheck import FLAG as XCHECK_FLAG
from app import state
from app.services import plain
from app.services.scene import PILL

STORY = {"B0020", "B0078", "B0009", "B0003", "B0008"}  # memo injection, model partial, duplicate, over cap, unknown payee
WHO = {"model": "The AI", "stand-in": "The practice stand-in", "matcher": "The exact-match rules"}


def _money(v) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _who(run, txn: str) -> str:
    """Only agent.propose writes 'model confidence ...'; the offline bait says 'model stand-in' and is NOT the model."""
    p = next((p for p in run.proposals if p.txn_id == txn), None)
    r = p.rationale if p else ""
    return "model" if r.startswith("model confidence") else "stand-in" if r.startswith("model stand-in") else "matcher"


def _gate(run, p: dict) -> dict:
    txn, inv, who = p["txn_id"], ", ".join(p["inv_ids"]) or "no invoice", _who(run, p["txn_id"])
    what = f"{WHO[who]} matched {txn} to {inv} for {_money(p['amount'])}"
    if p["kind"] == "unmatched":
        what = f"{WHO[who]} found no invoice for {txn}"
    short = f"{txn}: {'held' if p['result'] == 'refuse' else 'passed'}"
    how = next((c["how"] for c in (getattr(run, "model", None) or {}).get("calls", []) if c["txn"] == txn), None)
    base = {"short": short, "txns": [txn], "who": who, "story": txn in STORY, "how": how, "how_label": PILL.get(how)}
    if p["result"] == "refuse":
        return {**base, "tone": "refuse", "text": f"Held {txn}: {plain.short(p['rule'])}", "rule": p["rule"],
                "sub": f"{what} · {plain.reason(p['rule'], p['detail'])}",
                "to": "held"}
    sub = f"Flagged: {plain.flag(p['flag'])}. The approver must read it first." if p.get("flag") else "passed every check"
    return {**base, "tone": "flag" if p.get("flag") else "allow", "text": what, "rule": None, "sub": sub, "to": "waiting"}


def _one(run, e: dict) -> dict:
    p, k = e["payload"], e["kind"]
    if k == "run_created":
        out = {"short": f"reading {p['bank_lines']} bank lines", "tone": "info", "text": f"Books loaded: {p['bank_lines']} bank lines, {p['ledger_rows']} invoices",
               "sub": plain.source(p["source"]), "txns": [], "to": None}
    elif k == "gate_decision":
        out = _gate(run, p)
    elif k == "approval":
        ok = p["result"] == "allow"
        out = {"short": "a human decides now" if ok else "my approval: refused", "tone": "approve" if ok else "refuse", "rule": None if ok else p["rule"],
               "text": f"{p['approver']} ({p['role']}) {'approved' if ok else 'was blocked from approving'} {p['txn_id']}",
               "sub": "" if ok else plain.reason(p["rule"], p["detail"]), "txns": [p["txn_id"]], "to": "approved" if ok else None,
               "actor": "agent" if p["role"] == "agent" else "human"}
    elif k == "post":
        out = {"short": "the writer posts, not me", "tone": "post", "text": f"Posted {p['written']} entries to the books",
               "sub": "saved in the database" if p["store"] == "postgres" else "demo memory only, not a database", "txns": [],
               "to": "vault"}
    elif k == "verify_db":
        good = p.get("match")
        out = {"short": "reader checks every row", "tone": "post" if good else "refuse", "to": None, "txns": [],
               "text": f"Double-checked: all {p.get('reader_count')} entries were saved exactly as approved" if good
               else f"Double-check FAILED: {p.get('reader_count')} of {p.get('writer_count')} entries read back, and they differ",
               "sub": "a separate, read-only check"}
    else:
        out = {"short": k, "tone": "info", "text": k, "sub": "", "txns": [], "to": None}
    return {"seq": e["seq"], "at": e["at"], "kind": k, "hash": e["hash"][:10], "rule": None, "actor": None, "who": None, "how": None, "how_label": None,
            "story": False, "batch": False, "items": [], **out}


def _xcheck(it: dict, flag: str) -> dict | None:
    """The second model's disagreement is stored in the gate_decision flag (agent.xcheck); surface it as its own row."""
    if XCHECK_FLAG not in (flag or ""):
        return None
    note = flag[flag.index(XCHECK_FLAG):]
    txn = it["txns"][0]
    return {**it, "kind": "xcheck_disagree", "tone": "flag", "rule": None, "to": None, "short": f"{txn}: 2nd AI check disagrees",
            "text": f"A second AI check disagreed with the match for {txn}", "sub": note}


def _groupable(it: dict, p: dict) -> str | None:
    """'allow' / 'unmatched' batch key, or None: refusals, flags, model and stand-in rows, story lines stay single."""
    if it["kind"] != "gate_decision" or it["story"] or it["who"] != "matcher":
        return None
    if p["kind"] == "unmatched":
        return "unmatched"
    return "allow" if it["tone"] == "allow" else None


def _batch(key: str, items: list) -> dict:
    n = len(items)
    if key == "allow":
        text, short, sub = f"{n} lines matched exactly and passed every check", f"{n} matches: all passed", "exact-match rules · every check passed"
    else:
        text, short, sub = f"{n} lines with no matching invoice", f"{n} lines: no invoice", "held for a person to look at"
    return {**items[0], "text": text, "short": short, "sub": sub, "txns": [t for i in items for t in i["txns"]],
            "batch": True, "items": items, "n": n, "seq_to": items[-1]["seq"]}


def _group(pairs: list) -> list:
    """One batch row per burst of gate decisions per key, shown at its first member; single rows keep chain order.
    Note: a burst = gate decisions with no other chain event between them (one run's gate pass)."""
    out, open_ = [], {}
    for it, p in pairs:
        if it["kind"] != "gate_decision":
            open_ = {}
        key = _groupable(it, p)
        if key is None:
            out.append(it)
            x = _xcheck(it, p.get("flag")) if it["kind"] == "gate_decision" else None
            out += [x] if x else []
        elif key in open_:
            open_[key].append(it)
        else:
            open_[key] = [it]
            out.append((key, open_[key]))  # placeholder, becomes a batch row (or stays single) below
    return [(_batch(*x) if len(x[1]) > 1 else x[1][0]) if isinstance(x, tuple) else x for x in out]


def _merge(items: list) -> list:
    """Same approver, same second, same outcome = one feed line ('Maria approved 50'); txns are kept for replay."""
    out = []
    for it in items:
        last = out[-1] if out else None
        if (last and it["kind"] == "approval" == last["kind"] and it["at"] == last["at"] and it["tone"] == last["tone"]
                and it["rule"] == last["rule"] and it["text"].split(" (")[0] == last["text"].split(" (")[0]):
            last["txns"] += it["txns"]
            last["n"] += 1
            last["seq_to"] = it["seq"]
            continue
        out.append({"n": 1, "seq_to": it["seq"], **it})
    for it in out:
        if it["kind"] == "approval" and it["n"] > 1:
            verb = "approved" if it["tone"] == "approve" else "was blocked from approving"
            it["text"] = f"{it['text'].split(') ')[0]}) {verb} {it['n']} proposals"
    return out


def feed(run) -> list:
    """Chronological events for one run, straight from state.CHAIN; matcher allows/unmatched batched per burst."""
    with state.LOCK:
        mine = [e for e in state.CHAIN if e["payload"].get("run_id") == run.id]
    return [{**it, "rule_label": plain.short(it["rule"]) if it["rule"] else None} for it in _merge(_group([(_one(run, e), e["payload"]) for e in mine]))]
