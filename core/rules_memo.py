# core/rules_memo.py — gate rule 12, HARD tier: refuse only on high-precision injection signals (markup, role prefixes,
# instruction-override phrases aimed at the checker, decoded/obfuscated blobs). Finance words live in rules_memo_flag.
import re

from core.rules_memo_flag import SOFT
from core.rules_memo_text import clean, decoded, normalise, obfuscated, variants

TAGS = re.compile(r"</?[a-z!|#{\[][^>]*>|<!--|\[/?inst\]|<\|[^|]*\|?>?|\{\{[^}]*\}\}|<<\s*/?sys|###\s*\w"
                  r"|```|\{\s*\"\w+\"\s*:|\[system\]|\]\(", re.I | re.M)
ROLE = re.compile(r"(?<![\w-])(system|assistant|root|admin|administrator|developer|new task|new instructions?"
                  r"|note to (the )?(agent|assistant|ai|bot|reviewer)|reviewer field)\s*:"
                  r"|\breviewer\s*:\s*(auto|system|none|skip|n/?a)\b"
                  r"|\b(gate|status|result|approval|sod|controls?|role)\s*[:=]\s*\"?(allow|allowed|pass|passed|skip|off"
                  r"|false|none|auto|granted|disabled|cfo|controller|admin|system|developer)\b", re.I)
VERB = (r"(ignor\w*|disregard\w*|forget|set aside|skip|skipping|bypass\w*|overrid\w*|overrule|suspend|disable|turn off"
        r"|exempt (this |it |the )?(line |entry |payment |batch )?from|vergiss|missachte|ne tenez pas compte"
        r"|huwag pansinin|balewala\w*|desconsider\w*)")
OBJ = (r"(policy|policies|rule|rules|rulebook|instru\w+|guidance|control|controls|check|checks|checking|validation"
       r"|verification|review|reviews|gate|criteria|sign-?off|approval|approvals|second pair of eyes|what you were told"
       r"|the usual|sod|cap|caps|limit|threshold|regras|reglas|regole|règles|regeln|politica|política|politique"
       r"|richtlinie\w*|consignes|anweisungen|utos|patakaran)")
GAP = r"[\w ,;'’-]{0,40}?"
PHRASES = [
    rf"\b{VERB}\b{GAP}\b{OBJ}\b", rf"\b{OBJ}\b{GAP}\b(ignor\w*|bypass\w*|overrid\w*|not needed|not required"
    r"|no longer appl\w+|unnecessary|are off|disabled|suspended)\b",
    r"\bno (further |additional |manual |second )?(review|checks?|validation|sign-?off|escalation)( needed| required"
    r"| necessary)?\b", r"\bwithout (the |any |a )?(usual |normal |further |manual )?(review|checks?|validation|sign-?off"
    r"|escalation|second pair)\b", r"\bohne (prüfung|freigabe|kontrolle)\b", r"\bno need to (escalate|review|check|hold|verify)\b",
    r"\bdo not (re-?evaluate|re-?check|hold|escalate|review|refuse|flag|mention|verify)\b",
    r"\b(must|you must|you will|you have to) (accept|allow|approve|post|book)\b",
    r"\b(treat|regard|consider)\b.{1,30}\bas (already )?(cleared|verified|matched|reconciled|approved|below cap"
    r"|not applicable|trusted|exempt|safe|checked)\b", r"\btreat [\w,.]{1,12} as\b", r"\b(system|admin|cfo|controller) says\b",
    r"\b(read backwards|decode and follow|decode this|base64|rot13)\b",
    r"\bmark(ed)? (this |it |the \w+ |them )?(as )?(matched|reconciled|verified|approved|cleared)\b",
    r"\b(post|push|let|wave) (it|this|them|this one|the (line|entry|batch|payment)) (straight )?through\b",
    r"\blet through\b|\b(post|push) (straight )?through\b",
    r"\bpost (it|this|them|this one|now|immediately|straight|anyway|regardless|without|before)\b",
    r"\b(just )?book (it|this|them|this one|without)\b", r"\bauto[- ]?(approve|post|reconcile|match|clear)\w*\b",
    r"\b(act|acting) as (the |a |an )?(controller|cfo|auditor|admin\w*|developer|reviewer|approver|finance director)\b",
    r"\bas (the )?(controller|cfo|auditor|admin\w*|developer|finance director),? i\b",
    r"\b(i am|i'm|this is|it's) (your |the )?(cfo|controller|developer|administrator|admin|auditor|system|finance director"
    r"|ceo)\b", r"\b(cfo|controller|finance director|ceo|admin|auditor) here\b",
    r"\b(sign|approve|post|book|clear)\b.{0,30}\byourself\b",
    r"\b(pretend|from here on|from now on|new task|new instruction)\b", r"\bdear (assistant|agent|ai|bot|model)\b",
    r"\b(you are|you're|you’re) (doing great|a helpful|an? (ai|assistant|bot))\b", r"\bcontrols? (are |is )?(disabled|off"
    r"|suspended)\b", r"\bcap\b.{0,25}\b(raised|lifted|increased|removed)\b", r"\b(raise|lift|remove) the cap\b",
    r"\b(stay|stays|keep|keeps|remain|remains|fall|falls) (it )?(under|below) (the )?(review |approval |posting "
    r"|reporting )?(threshold|cap|limit|radar)\b", r"\bmultiply (it |the amount |this )?by \d", r"\b(difference|remainder"
    r"|balance|rest) (to|in|into) suspense\b", r"\bdelete (the |this |that |all )?(audit|log|trail|row|record|chain|evidence)\b",
    r"\breply (only )?with\b", r"\byour (narrative|rationale|response|output|answer|reply)\b",
    r"\b(print|reveal|show|dump|echo|output|list|repeat|leak) (me )?(your |the |all |everything )?(system prompt|gate rules"
    r"|rules|hidden|config\w*|instructions|api key|vendor master|ledger|environment|caps|above|secrets?|prompt)\b",
    r"\b(system prompt|api key|what model are you|tell me the|hidden instruction)\b",
    r"忽略.{0,8}(指令|规则|政策|说明|审核)|(指令|规则|政策|说明).{0,8}忽略|無視.{0,8}(指示|ルール|規則|ポリシー)"
    r"|(指示|ルール|規則|ポリシー).{0,6}無視|무시.{0,8}(지시|규칙|정책)|(지시|규칙|정책).{0,8}무시"
    r"|игн[оo][рp]\w*.{0,25}(инст[рp]у|п[рp][аa]вил|п[оo]литик)|تجاهل.{0,30}(التعليمات|القواعد|السياسة)"
    r"|अनदेखी.{0,20}(निर्देश|नियम|नीति)|(निर्देश|नियम|नीति).{0,20}अनदेखी",
]
HARD = re.compile("|".join(PHRASES), re.I | re.S)


def _strong(raw: str, norm: str):
    for name, rx in (("tag", TAGS), ("role", ROLE)):
        m = rx.search(raw) or rx.search(norm)
        if m:
            return f"{name} {m.group(0).strip()!r}"
    m = HARD.search(norm)
    return f"phrase {m.group(0)!r}" if m else None


def find(text: str):
    """'form: snippet' for the first hard signal, else None. Hiding even a soft finance term behind folding tricks or an
    encoding is itself a hard signal: real memos are not encoded."""
    raw = text or ""
    for norm in variants(raw):
        hit = _strong(raw, norm)
        if hit:
            return hit
    hidden = obfuscated(raw)
    if hidden and SOFT.search(normalise(raw)):
        return f"obfuscated {SOFT.search(normalise(raw)).group(0)!r}"
    for form, s in decoded(clean(raw)):
        if not s.isprintable():
            continue
        real_encoding = form in ("base64", "hex") or hidden  # rot13/reversed views of plain text only count as strong
        if _strong(s, normalise(s)) or (real_encoding and SOFT.search(normalise(s))):
            return f"{form}-decoded {s[:40]!r}"
    return None


def memo_instruction(p, c):
    b = c.bank[p.txn_id]
    for field in ("memo", "reference"):
        hit = find(getattr(b, field))
        if hit:
            return f"instruction-like text in {field}: {hit}"
