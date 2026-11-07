# app/routes/pages.py — landing page, console entry, benchmark page and health check.
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app import config, state
from app.services import attempts, bench, events, ledger, posting, runs, scene
from app.services.proposals import model_mode
from app.web import render
from core.csvload import load_bank, load_ledger
from core.gate import RULES

router = APIRouter()


def _latest():
    return next((r for r in reversed(state.RUNS.values()) if not r.uploaded), None)  # uploaded runs stay unlisted


def _room(run) -> dict:
    """The landing's room frame: the latest real run's state, or an empty room if nothing has run yet."""
    if run is None:
        return {"toks": [], "sc": None, "events": []}
    rows = runs.rows(run)
    return {"toks": scene.tokens(rows), "sc": scene.summary(run, rows), "events": events.feed(run)}


@router.get("/")
def home():
    return RedirectResponse("/stage", status_code=307)  # judges land on the scan room; the old landing lives at /about


@router.get("/about")
def index(request: Request):
    return render(request, "index.html", **_room(_latest()), **bench.measured(), tc=attempts.counter(), store=posting.store_name(), n_rules=len(RULES), n_bank=len(load_bank(config.BANK_CSV)),
                  n_ledger=len(load_ledger(config.LEDGER_CSV)))


@router.get("/console")
def console(request: Request, watch: int = 0):
    """Latest synthetic run if there is one (uploaded runs stay unlisted), else an empty console with the run button."""
    latest = _latest()
    if latest:
        return RedirectResponse(f"/runs/{latest.id}" + ("?watch=1" if watch else ""), status_code=303)
    return render(request, "console_empty.html", run=None, watch=watch)


@router.get("/bench")
def bench_page(request: Request):
    return render(request, "bench.html", **bench.measured(), off=bench.load("gate_off"))


def _db() -> str:
    if not config.writer_dsn():
        return "stub"
    try:
        import psycopg
        with psycopg.connect(config.writer_dsn(), connect_timeout=2) as c:
            c.execute("SELECT 1")
        return "ok"
    except Exception as e:  # noqa: BLE001 — health must report, not crash
        return f"error: {type(e).__name__}"


@router.get("/healthz")
def healthz():
    return {"db": _db(), "model": model_mode(),
            "chain_ok": ledger.verify()["ok"], "runs": len(state.RUNS)}
