# app/services/assist.py — the Closeguard assistant in the bookkeeper app: says what it found, offers to draft the supplier emails, hears yes or no.
import re

from app import state
from app.services import app_bank, app_view, mail, stage_voice

YES = re.compile(r"\b(yes|yeah|yep|yup|please|sure|ok(ay)?|do it|go ahead|draft|send)\b")
NO = re.compile(r"\b(no|nope|don'?t|not now|later|skip|cancel)\b")


def _facts():
    s = app_view.state()
    return s["bills"], app_bank.view(s["bills"]), bool(s.get("scanning"))


def is_yes(text: str):
    """True / False / None (not understood). 'no' wins over 'yes' so 'no, don't' is never read as consent."""
    t = text.lower()
    return False if NO.search(t) else True if YES.search(t) else None


def offer() -> dict | None:
    bills, bank, busy = _facts()
    items = mail.offer(bills, bank)
    if busy or not items:
        return None
    if len(items) == 1:
        text = f"I found a problem: {items[0][2]}. Do you want me to draft an email to {items[0][1]}?"
    else:
        who = sorted({x[1] for x in items})
        names = ", ".join(who[:-1]) + " and " + who[-1] if len(who) > 1 else who[0]
        text = f"I found {len(items)} problems that need the supplier: {names}. Do you want me to draft the emails?"
    return {"keys": [x[0] for x in items], "text": text, "say": stage_voice._say(text), "items": [x[2][0].upper() + x[2][1:] for x in items] if len(items) > 1 else []}


def answer(keys: list, text: str, heard: str | None) -> dict:
    yes = is_yes(text)
    if yes is None:
        return {"ok": False, "reply": stage_voice._say(f"Sorry, I heard: {text}. Say yes to draft the emails, or no.")}
    bills, bank, _ = _facts()
    who = mail.decide(keys, yes, bills, bank)
    with state.LOCK:
        state.log("email_consent", {"keys": keys, "by": "Ana (bookkeeper)", "text": text, "heard": heard, "draft": yes})
    if not yes:
        return {"ok": True, "drafted": [], "reply": stage_voice._say("Okay, no emails for now. The payments stay on hold.")}
    n = f"the email to {who[0]}" if len(who) == 1 else f"{len(who)} emails"
    return {"ok": True, "drafted": who, "reply": stage_voice._say(f"Noted. I drafted {n}. You will find {'it' if len(who) == 1 else 'them'} in Emails, ready for you to check and send.")}
