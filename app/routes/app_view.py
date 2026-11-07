# app/routes/app_view.py — the bookkeeper's desktop app (/app): bills in, plain status, what to do next. Also shown on the 3D PC.
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.services import app_activity, app_bank, app_money, app_view, bank_lock, mail, signin, vault, vault_s3
from app.web import render

router = APIRouter()


@router.get("/app")
def page(request: Request, embed: int = 0):
    return render(request, "app.html", embed=bool(embed))


@router.get("/app/state")
def state():
    s = app_view.state()
    bank = app_bank.view(s["bills"])
    due = app_money.due(s["bills"], bank)
    s["summary"]["pay"] = app_money.to_pay(s["bills"], due)  # "ready to pay" = checked and not paid yet
    return {**s, "bank": bank, "stopped": app_money.stopped(s["bills"], bank), "due": due,
            "activity": app_activity.feed(s["bills"])}


@router.get("/app/report")
def report(request: Request, saved: str = "", err: str = ""):
    """One page for the owner at month end: same numbers as the app, nothing new computed here."""
    d = state()
    mails = list(mail.THREADS.values())
    return render(request, "app_report.html", d=d, today=app_money.plain_date(d["due"]["today"]), active="report", pay=f"/simple/pay/{d['bank']['run']}" if d["bank"]["run"] and d["bank"]["ok"] else None,
                  mail_open=[t for t in mails if t["status"] in ("draft", "waiting", "replied", "no_reply", "flagged", "promised")],
                  mail_done=[t for t in mails if t["status"] == "done"], vault=vault.saved(), saved=saved, err=err, lock=bank_lock.status, demo_pin=signin.demo_pin())


@router.post("/app/report/vault")
def save_proof(pin: str = Form("", max_length=12)):
    """Maria saves the month's proof pack to Vultr Object Storage (it holds the QuickBooks file, so her PIN). The save is chained."""
    if err := signin.check("Maria", pin, "save the month's proof"):
        return RedirectResponse(f"/app/report?err={quote(err)}", status_code=303)
    try:
        out = vault.save("Maria")
    except vault_s3.VaultError as e:
        return RedirectResponse(f"/app/report?err={quote(str(e)[:200])}", status_code=303)
    return RedirectResponse(f"/app/report?saved={quote(out['key'].rsplit('/', 1)[-1])}", status_code=303)


@router.post("/app/report/vault/get")
def get_proof(name: str = Form(..., max_length=120), pin: str = Form("", max_length=12)):
    """Download a saved pack: Maria's PIN, then a 5-minute signed link straight from Vultr Object Storage. Chained."""
    if err := signin.check("Maria", pin, "download the month's proof"):
        return RedirectResponse(f"/app/report?err={quote(err)}", status_code=303)
    try:
        return RedirectResponse(vault.link(name, "Maria"), status_code=303)
    except (vault_s3.VaultError, ValueError) as e:
        return RedirectResponse(f"/app/report?err={quote(str(e)[:200])}", status_code=303)
