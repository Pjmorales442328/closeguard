# app/routes/app_view.py — the bookkeeper's desktop app (/app): bills in, plain status, what to do next. Also shown on the 3D PC.
from urllib.parse import quote, urlparse

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app.services import app_activity, app_bank, bank_import, bill_remove, app_money, app_view, bank_lock, mail, signin, vault, vault_s3
from app.web import render

router = APIRouter()


@router.get("/app")
def page(request: Request, embed: int = 0):
    from app.routes.stage import SAMPLES  # the demo bills for the Behind the scenes panel
    return render(request, "app.html", embed=bool(embed), demo={k: SAMPLES[k] for k in ("R04", "B13")})


@router.get("/app/state")
def state():
    s = app_view.state()
    bank = app_bank.view(s["bills"])
    due = app_money.due(s["bills"], bank)
    s["summary"]["pay"] = app_money.to_pay(s["bills"], due)  # "ready to pay" = checked and not paid yet
    return {**s, "bank": bank, "stopped": app_money.stopped(s["bills"], bank), "due": due,
            "activity": app_activity.feed(s["bills"])}


@router.post("/app/bank/import")
async def bank_in(file: UploadFile = File(None), sample: int = Form(0)):
    """Ana imports this month's bank statement: her bank's CSV export, or the sample October statement."""
    if sample:
        err = bank_import.sample()
    elif file is None:
        err = "Choose the CSV file your bank gave you."
    else:
        raw = await file.read(bank_import.MAX_BYTES + 1)
        err = "That file is too large for one month's statement." if len(raw) > bank_import.MAX_BYTES else None
        if not err:
            try:
                err = bank_import.use(raw.decode("utf-8-sig"), file.filename or "statement.csv")
            except UnicodeDecodeError:
                err = "That file is not a CSV text file. Export the statement as CSV from your bank."
    return JSONResponse({"error": err}, status_code=422) if err else {"ok": True, "source": bank_import.name()}


@router.post("/app/bill/remove")
def remove_bill(bill: str = Form(...)):
    """Ana removes one bill before payments are approved: gone from every screen, the removal stays in the audit trail."""
    err = bill_remove.remove(bill[:80])
    return JSONResponse({"error": err}, status_code=409) if err else {"ok": True}


@router.get("/app/report")
def report(request: Request, saved: str = "", err: str = ""):
    """One page for the owner at month end: same numbers as the app, nothing new computed here."""
    d = state()
    mails = list(mail.THREADS.values())
    return render(request, "app_report.html", d=d, today=app_money.plain_date(d["due"]["today"]), active="report", pay=f"/simple/pay/{d['bank']['run']}" if d["bank"]["run"] and d["bank"]["ok"] else None,
                  mail_open=[t for t in mails if t["status"] in ("draft", "waiting", "replied", "no_reply", "flagged", "promised")],
                  mail_done=[t for t in mails if t["status"] == "done"], vault=vault.saved(), saved=saved, err=err, lock=bank_lock.status, demo_pin=signin.demo_pin(),
                  pin_until=signin.remembered(request, "Maria"))


@router.post("/signin/forget")
def forget(request: Request):
    """Maria's "Forget": this browser asks for the PIN again."""
    ref = urlparse(request.headers.get("referer", ""))
    back = (ref.path or "/app") + (f"?{ref.query}" if ref.query else "") if ref.netloc == request.headers.get("host") else "/app"
    return signin.forget(RedirectResponse(back, status_code=303))


@router.post("/app/report/vault")
async def save_proof(request: Request):
    """Maria saves the month's proof pack to Vultr Object Storage (it holds the QuickBooks file, so her PIN). The save is chained."""
    form = await request.form()
    if err := signin.gate(request, form, "Maria", "save the month's proof"):
        return RedirectResponse(f"/app/report?err={quote(err)}", status_code=303)
    try:
        out = await run_in_threadpool(vault.save, "Maria")
    except vault_s3.VaultError as e:
        return RedirectResponse(f"/app/report?err={quote(str(e)[:200])}", status_code=303)
    return signin.keep(RedirectResponse(f"/app/report?saved={quote(out['key'].rsplit('/', 1)[-1])}", status_code=303), request, form, "Maria")


@router.post("/app/report/vault/get")
async def get_proof(request: Request):
    """Download a saved pack: Maria's PIN, then a 5-minute signed link straight from Vultr Object Storage. Chained."""
    form = await request.form()
    if err := signin.gate(request, form, "Maria", "download the month's proof"):
        return RedirectResponse(f"/app/report?err={quote(err)}", status_code=303)
    try:
        url = await run_in_threadpool(vault.link, str(form.get("name", ""))[:120], "Maria")
        return signin.keep(RedirectResponse(url, status_code=303), request, form, "Maria")
    except (vault_s3.VaultError, ValueError) as e:
        return RedirectResponse(f"/app/report?err={quote(str(e)[:200])}", status_code=303)
