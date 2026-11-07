# app/services/stage_log.py — the server's real audit-chain entries as short log lines for the 3D scan room's log panel.
import functools
import json
import os
import socket
import urllib.request

from agent.extract import MODELS
from app import config, state
from app.services import plain

READER = dict(zip(MODELS, plain.READERS))
MAX = 200


def _line(e: dict) -> str:
    p, k = e["payload"] if isinstance(e["payload"], dict) else {}, e["kind"]
    if k == "bill_received":
        return f"bill {p.get('bill_id')} received: {p.get('bytes')} bytes {p.get('mime')} sha256 {str(p.get('sha256'))[:12]}"
    if k == "bill_read":
        how = "saved answer" if p.get("cached") else "LIVE call to Vultr Serverless Inference"
        ok = "read" if p.get("fields") != "unreadable" else "could NOT read"
        lat = p.get("latency_s")
        rid = (p.get("vultr") or {}).get("id")
        return (f"{READER.get(p.get('model'), '?')} ({p.get('model')}) {ok} bill {p.get('bill_id')}" + (f" in {lat:.2f} s" if lat else "") + f" · {how}"
                + (f" · Vultr request id {rid}" if rid else ""))
    if k == "bill_checked":
        bad = sorted({c["rule"] for c in p.get("checks", []) if c.get("result") == "refuse"})
        diffs = p.get("diffs") or []
        return f"checks on {p.get('bill_id')}: {p.get('status')}" + (f" · failed {', '.join(bad)}" if bad else "") + (f" · readers differ on {', '.join(diffs)}" if diffs else "")
    if k == "gate_decision":
        inv = ",".join(p.get("inv_ids") or []) or "no bill"
        return f"gate: bank {p.get('txn_id')} {p.get('amount')} -> {inv}: {p.get('result')}" + (f" {p.get('rule')}" if p.get("rule") else "")
    if k == "voice_answer":
        return f"Ana answered on {p.get('bill_id')}: \"{p.get('text')}\"" + (" (spoken, Vultr Whisper)" if p.get("heard") else " (typed)") + (f" -> noted {p.get('noted')}" if p.get("noted") else "")
    if k == "bill_confirmed":
        return f"bill {p.get('bill_id')} confirmed by {p.get('who')} ({p.get('role')}): {p.get('result')}" + (f" {p.get('rule')}" if p.get("rule") else "")
    if k == "intake_run":
        return f"close run {p.get('run_id')} from {len(p.get('bill_ids', []))} bills"
    if k == "approval":
        return f"approval {p.get('txn_id')} by {p.get('approver')} ({p.get('role')}): {p.get('result')}" + (f" {p.get('rule')}" if p.get("rule") else "")
    if k == "post":
        return f"posted {p.get('written')} entries to {p.get('store')}"
    if k == "verify_db":
        return f"read-back check: {p.get('reader_count')} of {p.get('writer_count')} entries match: {p.get('match')}"
    if k == "email_sent":
        return f"email to {p.get('to')} approved and sent by {p.get('approved_by')}: \"{p.get('subject')}\" (demo outbox)"
    if k == "email_followup":
        return f"follow-up #{p.get('n')} sent to {p.get('to')} on schedule (demo outbox)"
    if k == "email_consent":
        return f"Ana answered \"{p.get('text')}\"" + (" (spoken, Vultr Whisper)" if p.get("heard") else "") + (f": draft {len(p.get('keys') or [])} email(s)" if p.get("draft") else ": no email for now")
    if k == "email_reply":
        return (f"reply from {p.get('from')} read" + (f" by {p.get('model')} on Vultr" if p.get("vultr") else "") + f": {p.get('intent')}"
                + (" · POSSIBLE SCAM: asks to change bank details, nothing changed" if p.get("scam") else ""))
    return k.replace("_", " ")


@functools.cache
def vultr_vm() -> dict:
    """Ask the Vultr metadata service who this machine is; it only answers on a Vultr instance. {} elsewhere."""
    try:
        d = json.load(urllib.request.urlopen("http://169.254.169.254/v1.json", timeout=1))
        return {"hostname": d.get("hostname"), "region": (d.get("region") or {}).get("regioncode"), "instance": d.get("instance-v2-id")}
    except (OSError, ValueError):
        return {}


def server() -> dict:
    return {"host": os.environ.get("CG_HOST_LABEL", "") + f" · container {socket.gethostname()}" if os.environ.get("CG_HOST_LABEL") else socket.gethostname(), "ai": "live calls on" if config.model_live() else "offline",
            "books": "Postgres" if config.writer_dsn() else "memory (demo)", "vm": vultr_vm()}


def since(after: int) -> dict:
    """Entries with seq > after (at most MAX, newest last). Each line keeps its real seq, time and short hash."""
    with state.LOCK:
        new = [e for e in state.CHAIN[max(after, len(state.CHAIN) - MAX):]]
    return {"seq": new[-1]["seq"] if new else after, "server": server(),
            "lines": [{"seq": e["seq"], "at": e["at"][11:19], "kind": e["kind"], "text": _line(e), "hash": e["hash"][:10]} for e in new]}
