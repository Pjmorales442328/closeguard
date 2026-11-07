# agent/voice.py — speech-to-text, text-to-speech (Vultr Serverless Inference) and the no-LLM question parser.
import difflib
import os
import re
from dataclasses import dataclass

STT_MODEL, TTS_MODEL, VOICE = "whisper-large-v3-turbo", "chatterbox", "default"  # Chatterbox (Resemble AI): natural English; qwen3-tts serena sounded Chinese
BASE_URL = "https://api.vultrinference.com/v1"
_DIGITS = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine".split())} | {"oh": "0", "buy": "8"}  # "buy" = whisper's mishearing of "eight" after "seven" (seen in the probe)
_SLOT = {"o": "0", "t": "7", "b": "8", "s": "5", "l": "1", "i": "1", "z": "0"}  # letters whisper hears for digits
_ROLES = ("controller", "cfo", "ap clerk", "agent")


def _client(timeout: float):
    from openai import OpenAI  # lazy: tests with a fake call never need the SDK or a key

    return OpenAI(api_key=os.environ["VULTR_INFERENCE_KEY"], timeout=timeout, max_retries=0,
                  base_url=os.environ.get("VULTR_INFERENCE_BASE_URL", BASE_URL))


def transcribe(data: bytes, mime: str, call=None) -> str:
    """Audio bytes -> text. `call(data, mime, model)` is injectable for tests."""
    if call:
        return call(data, mime, STT_MODEL)
    ext = "wav" if "wav" in mime else "mp4" if "mp4" in mime else "webm"
    r = _client(20).audio.transcriptions.create(model=STT_MODEL, file=(f"q.{ext}", data, mime))
    return (r.text or "").strip()


def speak(text: str, fmt: str = "wav", call=None) -> bytes:
    """Text -> audio bytes (24 kHz mono). `call(text, model, voice, fmt)` is injectable for tests."""
    if call:
        return call(text, TTS_MODEL, VOICE, fmt)
    return _client(30).audio.speech.create(model=TTS_MODEL, voice=VOICE, input=text, response_format=fmt).content


def normalise_ids(text: str, known) -> tuple:
    """Fix spoken/misheard bank line ids against the run's real ids -> (text, note). note is None when nothing was off."""
    low = {k.lower(): k for k in known}
    t = re.sub(r"\b(" + "|".join(_DIGITS) + r")\b", lambda m: _DIGITS[m.group(1)], text.lower())
    note = None

    def fix(m):
        nonlocal note
        raw = re.sub(r"\s", "", m.group(1))
        cand = "b" + "".join(_SLOT.get(c, c) for c in raw)
        if not cand[1:].isdigit():
            return m.group(0)
        hit = low.get(cand) or next(iter(difflib.get_close_matches(cand, low, 1, 0.6)), None)
        if not hit:
            return m.group(0)
        hit = low.get(hit, hit)
        if "b" + raw != cand or cand not in low:
            note = f"I heard {('B' + raw).upper()}; closest line is {hit}."
        return hit

    return re.sub(r"\bb\s*((?:[0-9a-z]\s*){3}[0-9a-z])", fix, t).strip(), note


@dataclass
class Intent:
    name: str  # why | todo | summary | approve | bill_why | bill_read | help
    line: str | None = None
    who: str | None = None
    role: str | None = None


def parse(text: str, bill: bool = False) -> Intent:
    """First match wins. Text should already be id-normalised. `bill` = a scanned bill is on the desk."""
    t = text.lower().strip()
    line = next(iter(re.findall(r"\bb\d{4}\b", t)), None)
    line = line.upper() if line else None
    if line:
        return Intent("why", line)
    if bill and re.search(r"(why|what).*(hold|held|confirm|refused|wrong)", t):
        return Intent("bill_why")
    if bill and re.search(r"(what|read).*(bill|invoice|supplier|total)", t):
        return Intent("bill_read")
    if re.search(r"why .*(refused|rejected|blocked|held)", t):
        return Intent("why")
    if m := re.search(r"approve (?:all|everything)(?: allowed)?[ ,]*(.*)", t):
        rest = m.group(1)
        role = next((r for r in _ROLES if r in rest), None)
        name = re.sub(r"[^a-z ]", " ", rest.replace(role or "\0", " ")).split()
        return Intent("approve", who=" ".join(name[:2]).title() or None, role=role)
    if re.search(r"(left|remaining|still).*(approve|approval)|what.*approve", t):
        return Intent("todo")
    if re.search(r"summary|close|tonight|status", t):
        return Intent("summary")
    return Intent("help")


if __name__ == "__main__":
    ids = {"B0078": 1, "B0003": 1}
    assert "B0078 refused" in normalise_ids("Why was B zero zero T buy refused?", ids)[0]
    t, note = normalise_ids("why was b007b refused", ids)
    assert t == "why was B0078 refused" and "heard B007B" in note, (t, note)
    t, note = normalise_ids("why was b 0 0 7 9 refused", ids)
    assert "B0078" in t and note and "closest" in note, (t, note)
    assert parse("why was B0078 refused").line == "B0078"
    assert parse("what is left to approve").name == "todo"
    assert parse("Give me the close summary").name == "summary"
    a = parse("approve all allowed, Maria, controller")
    assert (a.name, a.who, a.role) == ("approve", "Maria", "controller"), a
    assert parse("why is this one on hold", bill=True).name == "bill_why"
    assert parse("tell me a joke").name == "help"
    print("ok")
