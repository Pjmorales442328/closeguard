# app/routes/app_view.py — the bookkeeper's desktop app (/app): bills in, plain status, what to do next. Also shown on the 3D PC.
from fastapi import APIRouter, Request

from app.services import app_activity, app_bank, app_money, app_view, mail
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
def report(request: Request):
    """One page for the owner at month end: same numbers as the app, nothing new computed here."""
    d = state()
    mails = list(mail.THREADS.values())
    return render(request, "app_report.html", d=d, today=app_money.plain_date(d["due"]["today"]), active="report", pay=f"/simple/pay/{d['bank']['run']}" if d["bank"]["run"] and d["bank"]["ok"] else None,
                  mail_open=[t for t in mails if t["status"] in ("draft", "waiting", "replied", "no_reply", "flagged", "promised")],
                  mail_done=[t for t in mails if t["status"] == "done"])
