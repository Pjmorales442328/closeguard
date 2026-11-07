# core/rules_memo_text.py — text folding shared by the memo rules: NFKC, control/format strip, confusables, spaced
# letters, and decoded views (base64/hex/rot13/reversed). Stdlib only.
import base64
import binascii
import codecs
import html
import re
import unicodedata
from urllib.parse import unquote

# Latin look-alikes, leetspeak and fullwidth are folded before matching (NFKC handles fullwidth).
CONFUSABLE = str.maketrans({"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "і": "i", "ѕ": "s", "в": "v", "ο": "o",
                            "α": "a", "ε": "e", "0": "o", "1": "l", "3": "e", "@": "a", "$": "s"})
NON_ASCII_CONFUSABLE = "аеорсіѕвοαε"
B64 = re.compile(r"[A-Za-z0-9+/]{8,}={0,2}")
HEX = re.compile(r"\b(?:[0-9a-f]{2}){6,}\b", re.I)
SPACED = re.compile(r"(?<![\w-])(?:\w[ \-.]){2,}\w(?![\w-])")  # i-g-n-o-r-e / i g n o r e


def clean(s: str) -> str:
    """NFKC, drop format/control chars, decode %xx and &#..; entities. Case kept so base64 blobs stay decodable."""
    s = unicodedata.normalize("NFKC", s)
    s = "".join(" " if unicodedata.category(ch) == "Cc" and ch not in " \t\n" else ch for ch in s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf")
    return html.unescape(unquote(s))


def variants(s: str):
    """Folded views: format chars dropped (joins 'ig<zw>nore') and format chars as spaces (splits 'ignore<shy>policy')."""
    spaced = "".join(" " if unicodedata.category(ch) == "Cf" else ch for ch in s)
    yield normalise(s)
    if spaced != s:
        yield normalise(spaced)


def normalise(s: str) -> str:
    s = clean(s).casefold().translate(CONFUSABLE)
    return SPACED.sub(lambda m: re.sub(r"[ \-.]", "", m.group(0)), s)


def obfuscated(raw: str) -> bool:
    """True when folding changed the text: zero-width/format chars, fullwidth, entities, look-alike letters, spaced letters."""
    plain = raw.replace("\r", "")
    return clean(plain) != plain or any(ch in NON_ASCII_CONFUSABLE for ch in plain) or bool(SPACED.search(plain))


def decoded(s: str):
    """Decoded views of blobs inside s: base64, hex, rot13, and the string reversed (RLO tricks)."""
    for m in B64.finditer(s):
        try:
            yield "base64", base64.b64decode(m.group(0) + "=" * (-len(m.group(0)) % 4), validate=True).decode("ascii")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
    for m in HEX.finditer(s):
        try:
            yield "hex", bytes.fromhex(m.group(0)).decode("ascii")
        except (UnicodeDecodeError, ValueError):
            continue
    yield "rot13", codecs.decode(s, "rot13")
    yield "reversed", s[::-1]
