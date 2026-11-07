# app/routes/intake.py — "Bills in": upload bill photos, show both readings, human confirm/reject, run the close on them.
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from agent.extract import MODELS
from app import config
from app.services import intake, intake_human as human, intake_kit, intake_read, plain
from app.web import is_htmx, render, templates
from core.csvload import MAX_BYTES as CSV_MAX, CsvError, parse_bank
from core.gate import APPROVER_ROLES

router = APIRouter()
templates.env.globals["pick_fields"] = intake_read.pick_fields
PAGE = "bills.html"


def _batch(bid: str):
    b = intake.get(bid)
    if b is None:
        raise HTTPException(404, "bill batch not found (visitor batches are kept in memory only)")
    return b


def _card(b, n: int):
    c = next((c for c in b.cards if c.n == n), None)
    if c is None:
        raise HTTPException(404, "no such bill")
    return c


def _page(request, b, status_code=200, error=None):
    return render(request, PAGE, status_code=status_code, batch=b, error=error, roles=sorted(APPROVER_ROLES, reverse=True),
                  names=MODELS, live=config.model_live())


@router.get("/bills")
def show(request: Request, batch: str = "demo"):
    return _page(request, _batch(batch))


@router.post("/bills/demo/reset")
def reset_demo():
    intake.reset_demo()
    return RedirectResponse("/bills", status_code=303)


@router.get("/bills/kit.zip")
def kit():
    return Response(intake_kit.build(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="closeguard-demo-kit.zip"'})


@router.get("/bills/{bid}/cards")
def cards(request: Request, bid: str):
    return render(request, "partials/bill_cards.html", batch=_batch(bid), roles=sorted(APPROVER_ROLES, reverse=True),
                  names=MODELS)


@router.get("/bills/{bid}/{n}/image")
def image(bid: str, n: int):
    c = _card(_batch(bid), n)
    return Response(c.data, media_type=c.mime, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private"})


@router.post("/bills")
async def upload(request: Request, files: list[UploadFile] = File(None)):
    try:
        got = [(f.filename or "bill", await f.read(intake.MAX_BYTES + 1)) for f in (files or [])[: intake.MAX_FILES + 1]]
        b = intake.receive(got)
    except intake.IntakeRefused as e:  # a clear 400 with the reason, never a 500
        return _page(request, intake.demo(), 400, str(e))
    intake.start_reading(b)
    return RedirectResponse(f"/bills?batch={b.id}", status_code=303)


def _human(request, bid: str, n: int, who: str, role: str, picks):
    """picks = dict -> confirm with per-field picks; None -> reject."""
    b = _batch(bid)
    c = _card(b, n)
    if not who.strip():
        raise HTTPException(400, "name is required")
    d = human.confirm(b, c, who[:80], role[:20], picks) if picks is not None else human.reject(b, c, who[:80], role[:20])
    if is_htmx(request):
        return render(request, "partials/bill_card.html", batch=b, c=c, roles=sorted(APPROVER_ROLES, reverse=True),
                      names=MODELS)
    if d.result != "allow":
        return _page(request, b, 403, f"{plain.reason(d.rule, d.detail)} ({d.rule})")
    return RedirectResponse(f"/bills?batch={bid}", status_code=303)


def _picks(form) -> dict:
    """pick_<field> = 0 | 1 | other (text in other_<field>); 'reading' = whole-reading accept when only one reader read."""
    out = {}
    for k, v in form.items():
        if k.startswith("pick_"):
            out[k[5:]] = f"other:{form.get('other_' + k[5:], '')[:80]}" if v == "other" else str(v)
        elif k == "reading":
            out["*"] = str(v)
    return out


@router.post("/bills/{bid}/{n}/confirm")
async def confirm(request: Request, bid: str, n: int):
    form = await request.form()
    return _human(request, bid, n, str(form.get("who", "")), str(form.get("role", "")), _picks(form))


@router.post("/bills/{bid}/{n}/reject")
async def reject(request: Request, bid: str, n: int):
    form = await request.form()
    return _human(request, bid, n, str(form.get("who", "")), str(form.get("role", "")), None)


@router.post("/bills/{bid}/run")
async def run(request: Request, bid: str, bank: UploadFile = File(None)):
    b = _batch(bid)
    try:
        rows = None
        if bank is not None and bank.filename:
            raw = await bank.read(CSV_MAX + 1)
            if len(raw) > CSV_MAX:
                raise CsvError("bank file exceeds 2 MB")
            rows = parse_bank(raw.decode("utf-8-sig"))
        r = await run_in_threadpool(intake.make_run, b, rows)  # model calls must not hold the event loop (healthz stays up)
    except (CsvError, UnicodeDecodeError, intake.IntakeRefused) as e:
        return _page(request, b, 400, f"bank CSV: {e}" if isinstance(e, (CsvError, UnicodeDecodeError)) else str(e))
    return RedirectResponse(f"/runs/{r.id}", status_code=303)
