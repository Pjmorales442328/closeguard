# app/routes/runs.py — create a seeded run, show it, approve, post, and the try-to-trick-it box.
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.services import approvals, attempts, bench, books_export, events, explain, posting, runs, scene, trick
from app.web import is_htmx, render
from core.gate import RULES
from writer.db import PostRefused

router = APIRouter()


def _run(run_id: str):
    run = runs.get_run(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


def _body(request, run, line: str | None = None, **extra):
    """htmx gets the swappable body; a plain form post (no JS) gets the whole page."""
    rows = runs.rows(run)
    ctx = {"run": run, "rows": rows, "store": posting.store_name(), "events": events.feed(run),
           "toks": scene.tokens(rows), "sc": scene.summary(run, rows), "line": explain.pick(rows, line),
           "choices": explain.choices(rows), "zones": scene.ZONES, "n_rules": len(RULES), **extra}
    if is_htmx(request):
        return render(request, "partials/run_body.html", **ctx)
    m = bench.measured()
    return render(request, "run.html", tc=attempts.counter(), bench=m["b"], **m, **ctx)


@router.post("/runs")
def create(seed: int = 1, watch: int = 0, live: int = 0, live_form: str = Form("", alias="live")):
    """live=1 (query or the console checkbox) asks for real model calls; the server may still refuse (off / cooling down)."""
    if seed != 1:
        raise HTTPException(400, "only the synthetic seed run (seed=1) is available")
    run = runs.create_seed_run(live=bool(live) or live_form == "1")
    return RedirectResponse(f"/runs/{run.id}" + ("?watch=1" if watch else ""), status_code=303)


@router.get("/runs/{run_id}")
def show(request: Request, run_id: str, line: str | None = None, watch: int = 0):
    return _body(request, _run(run_id), line, watch=watch)


@router.get("/runs/{run_id}/proposals")
def table(request: Request, run_id: str):
    return _body(request, _run(run_id))


@router.post("/runs/{run_id}/approve")
def approve(request: Request, run_id: str, txn_id: str = Form(...), approver: str = Form(...), role: str = Form(...),
            ack: bool = Form(False)):
    run = _run(run_id)
    if not approver.strip():
        raise HTTPException(400, "approver name is required")
    ds = approvals.approve(run, txn_id.strip(), approver[:80], role[:20], ack)
    ok = sum(d.result == "allow" for d in ds)
    refused = [d for d in ds if d.result != "allow"]
    flash = {"ok": ok, "refused": refused[:5], "n_refused": len(refused), "who": approver, "role": role}
    return _body(request, run, flash=flash)


@router.post("/runs/{run_id}/post")
def post(request: Request, run_id: str):
    run = _run(run_id)
    try:
        posting.post(run)
        err = None
    except PostRefused as e:
        err = str(e)
    return _body(request, run, post_error=err)


@router.post("/runs/{run_id}/trick")
def trick_it(request: Request, run_id: str, memo: str = Form("")):
    t = trick.try_memo(_run(run_id), memo)
    return render(request, "partials/trick.html", t=t, tc=attempts.counter())


@router.get("/runs/{run_id}/books.csv")
def books(run_id: str):
    """Posted entries only, as a journal CSV for QuickBooks Online import (or any tool that imports journals)."""
    run = _run(run_id)
    if not run.posted:
        raise HTTPException(409, "nothing posted yet")
    return Response(books_export.csv_text(run), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="closeguard-{run_id}-journal.csv"'})
