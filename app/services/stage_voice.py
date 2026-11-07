# app/services/stage_voice.py — scan-room conversation: the server speaks a discrepancy, Ana answers, Maria confirms.
import re
import threading

from app import state
from app.services import desk, intake, mail, intake_human as human, plain, voice

PICKS: dict = {}  # bill id "batch/n" -> {field: "0" | "1"} from Ana's answers; Maria confirms them
_lock = threading.Lock()
NUM = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine".split())} | {"oh": "0"}
ORD = {w: str(i) for i, w in enumerate("zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth "
       "thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split())}
MONTHS = "january february march april may june july august september october november december".split()


def _say(text: str) -> dict:
    """Queue the sentence for Vultr TTS (served lazily by /voice/audio/{key}); the page falls back to the browser voice."""
    key = voice.audio_key(text)
    voice.PENDING[key] = text
    return {"text": text, "key": key}


def spoken(value: str) -> str:
    """'2026-11-02' -> 'November 2' so the voice says a date, not digits."""
    m = re.fullmatch(r"\d{4}-(\d\d)-(\d\d)", value)
    return f"{MONTHS[int(m[1]) - 1].capitalize()} {int(m[2])}" if m else value


def _norm(text: str) -> str:
    """Lower case, number words to digits, 'twenty second' -> '22', drop punctuation (whisper output varies)."""
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.lower())
    t = re.sub(r"twenty[\s-]*(\w+)", lambda m: "2" + (ORD.get(m[1]) or NUM.get(m[1]) or m[1]), t)
    t = " ".join(ORD.get(w) or NUM.get(w) or w for w in re.findall(r"[a-z]+|\d+", t))
    return t


def _variants(field: str, value: str) -> list:
    v = value.lower()
    out = [_norm(v), re.sub(r"\D", "", v)]
    m = re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", value)
    if m:
        mon, day = MONTHS[int(m[2]) - 1], str(int(m[3]))
        out += [f"{mon} {day}", f"{mon[:3]} {day}", f"{day} {mon}", f"{day} of {mon}", f"{int(m[2])} {day}"]
    return [x for x in out if x]


def match(options: list, heard: str):
    """Index of the one option the answer names, else None (ambiguous or neither)."""
    h = _norm(heard)
    hd = re.sub(r"\D", "", h)
    hit = [i for i, (f, val) in enumerate(options)
           if any((x.isdigit() and len(x) >= 3 and x in hd) or (not x.isdigit() and x in h) for x in _variants(f, val))]
    if len(hit) != 1 and all(re.sub(r"\D", "", v) for _, v in options):  # digits differ only at the end: compare the tails
        for k in (2, 3, 4):  # shortest tail that tells them apart ("the one ending in seven one")
            tails = [re.sub(r"\D", "", v)[-k:] for _, v in options]
            if len(set(tails)) == 2:
                hit = [i for i, t in enumerate(tails) if hd.endswith(t) or t in hd]
                break
    return hit[0] if len(hit) == 1 else None


def _open(v: dict) -> list:
    """Disagreeing fields Ana has not answered yet: [(field, value A, value B)]."""
    done = PICKS.get(v["id"], {})
    get = lambda r, f: next((x["v"] for x in r["fields"] if x["f"] == f), "")
    return [(f, get(v["readers"][0], f), get(v["readers"][1], f)) for f in v["diffs"] if f not in done and all(r["ok"] for r in v["readers"])]


def prompt(v: dict):
    """What the server says after a scan, or None when there is nothing to discuss."""
    if v["status"] == "confirm" and (q := _open(v)):
        f, a, b = q[0]
        return _say(f"Ana, the two readers disagree on the {plain.field(f)}. One read {spoken(a)}, the other {spoken(b)}. Which one is on the bill?")
    if v["status"] == "confirm":
        return _say("Thanks Ana. Maria, the controller, now has to confirm these values.")
    if v["status"] == "refused" and (o := _email_offer(v["id"])):
        return _say(f"Ana, I found a problem: {o[2]}. Do you want me to draft an email to {o[1]} asking for a corrected bill?")
    return None


def _email_offer(bill_id: str):
    from app.services import assist  # late import, assist imports this module for _say
    bills, bank, _ = assist._facts()
    return next((o for o in mail.offer(bills, bank) if o[0] == f"bill:{bill_id}"), None)


def answer(bill_id: str, text: str, heard: str | None) -> dict:
    """Ana's answer (typed or transcribed, already shown to her). Records it; never confirms a bill (only Maria can)."""
    v = desk.lookup(bill_id)
    if v is None:
        return {"reply": _say("I lost that bill. Scan it again."), "v": None}
    text = text.strip()[:200]
    note = None
    if v["status"] == "confirm" and (q := _open(v)):
        f, a, b = q[0]
        i = match([(f, a), (f, b)], text)
        if i is None:
            return {"reply": _say(f"Sorry, I heard: {text}. Please say {spoken(a)} or {spoken(b)}."), "v": v}
        with _lock:
            PICKS.setdefault(bill_id, {})[f] = str(i)
        note = f"{plain.field(f)} = {(a, b)[i]}"
        nxt = prompt(v)
    elif v["status"] == "refused" and _email_offer(bill_id):
        from app.services import assist
        r = assist.answer([f"bill:{bill_id}"], text, heard)
        return {**r, "v": v, "noted": ("draft the email" if r.get("drafted") else "no email") if r["ok"] else None, "ready_for_maria": False}
    else:
        nxt = _say("This bill has nothing to discuss: all checks pass.")
    with state.LOCK:
        state.log("voice_answer", {"bill_id": bill_id, "by": "Ana (bookkeeper)", "text": text, "heard": heard, "noted": note})
    return {"reply": nxt, "v": v, "noted": note, "ready_for_maria": v["status"] == "confirm" and not _open(v)}


def confirm(bill_id: str) -> dict:
    """Maria (controller) confirms Ana's picks: the real per-field merge + every check again, same rule as the Bills page."""
    bid, n = bill_id.rsplit("/", 1)
    b = intake.get(bid)
    c = next((c for c in b.cards if c.n == int(n)), None) if b else None
    if c is None:
        return {"error": "bill not found"}
    d = human.confirm(b, c, "Maria", "controller", dict(PICKS.get(bill_id, {})))
    from app.services import app_bank
    app_bank.rematch()  # a confirmed bill is matched with the bank right away
    v = desk.view(b, c)
    ok = d.result == "allow"
    return {"v": v, "reply": _say("Maria confirmed it. All checks pass on the corrected bill." if ok and v["status"] == "confirmed"
                                  else f"Not confirmed: {plain.reason(d.rule, d.detail)}")}
