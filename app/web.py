# app/web.py — shared Jinja2 templates and the htmx-or-full-page render helper.
import re
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from agent.extract import MODELS
from app import config
from app.services import plain, plain_entry
from core.rules_memo import HARD, ROLE, TAGS
from core.rules_memo_flag import SOFT

templates = Jinja2Templates(directory=Path(__file__).with_name("templates"))
_HARD = re.compile("|".join(r.pattern for r in (TAGS, ROLE, HARD)), re.I | re.M | re.S)


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def render(request: Request, name: str, status_code: int = 200, **ctx):
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def highlight(text: str) -> Markup:
    """Escape memo text; wrap hard injection signals in <mark> (red) and soft finance terms in <mark class=soft> (amber).
    Plain-text view only: folded/encoded tricks are caught by the gate even when nothing is marked here."""
    text = text or ""
    spans = [(m.start(), m.end(), "") for m in _HARD.finditer(text)] or [(m.start(), m.end(), ' class="soft"') for m in SOFT.finditer(text)]
    out, last = [], 0
    for a, b, cls in spans:
        if a < last:
            continue
        out += [escape(text[last:a]), Markup(f"<mark{cls}>"), escape(text[a:b]), Markup("</mark>")]
        last = b
    out.append(escape(text[last:]))
    return Markup("").join(out)


templates.env.filters["highlight"] = highlight


def status_chips(run=None) -> list:
    """Header chips with real values (same sources as /healthz): (css class, plain text, technical tooltip)."""
    from app.services import ledger
    v = ledger.verify()
    chain = ((("ok", "Audit trail: intact", f"{v['length']} entries, every hash recomputes") if v["ok"]
              else ("bad", "Audit trail: BROKEN", f"first bad entry #{v['first_bad_seq']}"))
             if v["length"] else ("", "Audit trail: empty", "no entries yet"))
    tech = "glm-5.3-flash on Vultr Serverless Inference"
    model = ("work", "AI: on (Vultr)", f"{tech}; the scan room always calls it live, the console uses saved answers first") if config.model_live()         else ("warn", "AI: off", "offline stand-in replays fixed proposals; no model is called")
    mode = (getattr(run, "model", None) or {}).get("mode")
    if mode == "live":
        ok = any(c["how"] == "live" for c in run.model["calls"])
        model = ("work", "AI: live", f"{tech}, called live this run") if ok else ("warn", "AI: live failed, saved answers used", tech)
    elif mode == "offline" and run is not None and not run.uploaded and config.model_live():
        model = ("warn", "AI failed this run: stand-in used", "offline stand-in replays fixed proposals")
    journal = ("post", "Books: saved in the database", "Postgres, append-only journal") if config.writer_dsn()         else ("warn", "Books: demo only", "in-memory demo store, no database configured")
    return [model, journal, chain]


templates.env.filters["reason"] = lambda d: plain.reason(*((d.get("rule"), d.get("detail")) if isinstance(d, dict) else (d.rule, d.detail)))
templates.env.filters["rule_short"] = plain.short
templates.env.filters["field"] = plain.field
templates.env.filters["money"] = plain.money
templates.env.filters["flag"] = plain.flag
templates.env.filters["rid"] = lambda r: Markup('<small class="muted rid">{}</small>').format(r) if r else ""
templates.env.globals["readers"] = plain.READERS
templates.env.globals["entry_text"] = plain_entry.entry
templates.env.filters["reader"] = lambda m: dict(zip(MODELS, plain.READERS)).get(m, m)
templates.env.globals["status_chips"] = status_chips
templates.env.globals["model_live"] = config.model_live
