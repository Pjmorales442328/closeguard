# app/routes/simple.py — the bookkeeper's phone view: scan bills, see OK / on hold / pick, approve, post, QuickBooks.
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from urllib.parse import quote

from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from app.services import app_pay, approvals, books_export, intake, signin, intake_human as human, intake_read, posting, runs
from app.web import render
from writer.db import PostRefused

router = APIRouter()
WHO, ROLE = "Maria", "controller"  # the demo's named controller; a login replaces this


def _batch(bid: str):
    b = intake.get(bid)
    if b is None:
        raise HTTPException(404, "these bills are gone (kept in memory only); scan again")
    return b


def _hold(c) -> str:
    """First plain reason a bill is held, '' when it is fine."""
    for ds in c.checks.values():
        for d in ds:
            if d.result == "refuse":
                return d
    return ""


def _new_supplier(c) -> bool:
    return any(d.flag for ds in c.checks.values() for d in ds)


@router.get("/simple")
def bills(request: Request, batch: str = "demo", error: str = ""):
    b = _batch(batch)
    order = {"confirm": 0, "refused": 1, "unreadable": 1, "rejected": 2, "received": 3, "ready": 4, "confirmed": 4}
    cards = sorted(b.cards, key=lambda c: (order.get(c.status, 5), c.n))
    return render(request, "simple.html", batch=b, cards=cards, hold=_hold, new_supplier=_new_supplier,
                  final=intake_read.final, pick_fields=intake_read.pick_fields, error=error)


@router.post("/simple/scan")
async def scan(request: Request, files: list[UploadFile] = File(None)):
    try:
        got = [(f.filename or "bill", await f.read(intake.MAX_BYTES + 1)) for f in (files or [])[: intake.MAX_FILES + 1]]
        b = intake.receive(got)
    except intake.IntakeRefused as e:
        return RedirectResponse(f"/simple?error={e}", status_code=303)
    await run_in_threadpool(intake.read_all, b)  # both readers, then the checks; the phone waits a few seconds
    return RedirectResponse(f"/simple?batch={b.id}", status_code=303)


@router.post("/simple/reset")
def reset():
    intake.reset_demo()
    return RedirectResponse("/simple", status_code=303)


@router.post("/simple/{bid}/{n}/pick")
async def pick(request: Request, bid: str, n: int):
    b = _batch(bid)
    c = next((c for c in b.cards if c.n == n), None)
    if c is None:
        raise HTTPException(404, "no such bill")
    form = await request.form()
    human.confirm(b, c, WHO, ROLE, {k[5:]: str(v) for k, v in form.items() if k.startswith("pick_")})
    return RedirectResponse(f"/simple?batch={bid}", status_code=303)


@router.post("/simple/{bid}/match")
async def match(bid: str):
    try:
        r = await run_in_threadpool(intake.make_run, _batch(bid), None)
    except intake.IntakeRefused as e:
        return RedirectResponse(f"/simple?batch={bid}&error={e}", status_code=303)
    return RedirectResponse(f"/simple/pay/{r.id}", status_code=303)


def _run(rid: str):
    run = runs.get_run(rid)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


@router.get("/simple/pay/{rid}")
def pay(request: Request, rid: str, note: str = "", err: str = ""):
    run = _run(rid)
    return render(request, "app_pay.html", run=run, v=app_pay.view(run), note=note, err=err, who=WHO, demo_pin=signin.demo_pin())


@router.post("/simple/pay/{rid}/approve")
async def approve(request: Request, rid: str):
    form = await request.form()
    run = _run(rid)
    if err := signin.check(WHO, form.get("pin", ""), f"approve payments in run {rid}"):
        return RedirectResponse(f"/simple/pay/{rid}?err={quote(err)}", status_code=303)
    approvals.approve(run, "*", WHO, ROLE, ack=form.get("ack") == "yes")
    return RedirectResponse(f"/simple/pay/{rid}", status_code=303)


@router.post("/simple/pay/{rid}/export")
async def export(request: Request, rid: str):
    """The QuickBooks file leaves the system only after Maria's PIN; the download is chained like any other step."""
    form = await request.form()
    run = _run(rid)
    if not run.posted:
        raise HTTPException(409, "nothing posted yet")
    if err := signin.check(WHO, form.get("pin", ""), f"export run {rid} to QuickBooks"):
        return RedirectResponse(f"/simple/pay/{rid}?err={quote(err)}", status_code=303)
    from app import state  # only this route logs here
    with state.LOCK:
        state.log("books_exported", {"run_id": rid, "by": WHO, "entries": len(run.posted)})
    return Response(books_export.csv_text(run), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="closeguard-{rid}-journal.csv"'})


@router.post("/simple/pay/{rid}/ai-approve")
def ai_approve(rid: str):
    """The proof moment: the AI asks to approve its own matches. The same rules as everywhere refuse it."""
    run = _run(rid)
    txn = next((p.txn_id for p in run.proposals if run.decisions[p.txn_id].result == "allow"), None)
    ds = approvals.approve(run, txn, "agent", "agent") if txn else []
    note = "ai-refused" if ds and all(d.result == "refuse" for d in ds) else "ai-check-failed"
    return RedirectResponse(f"/simple/pay/{rid}?note={note}", status_code=303)


@router.post("/simple/pay/{rid}/post")
def post(rid: str):
    try:
        posting.post(_run(rid))
    except PostRefused:
        return RedirectResponse(f"/simple/pay/{rid}?note=nothing-to-post", status_code=303)
    return RedirectResponse(f"/simple/pay/{rid}", status_code=303)
