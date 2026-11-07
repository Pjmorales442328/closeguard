# app/routes/mail.py — supplier email threads for the bookkeeper app: list, approve-and-send a draft, a supplier's (demo) reply.
from fastapi import APIRouter, Form, HTTPException
from starlette.concurrency import run_in_threadpool

from app.services import app_bank, app_view, assist, bank_lock, mail

router = APIRouter()


def _view(t: dict) -> dict:
    return {**t, "followup_s": mail.followup_seconds(), "lock": bank_lock.status(t["supplier"])}


@router.get("/mail/state")
def mail_state():
    s = app_view.state()
    mail.sync(s["bills"], app_bank.view(s["bills"]))
    order = {"flagged": 0, "draft": 1, "replied": 2, "no_reply": 3, "waiting": 4, "promised": 5, "done": 6}
    ts = sorted(mail.THREADS.values(), key=lambda t: (order.get(t["status"], 9), -t["msgs"][-1]["at"]))
    return {"threads": [_view(t) for t in ts], "demo": True, "offer": assist.offer()}


@router.post("/mail/offer")
def offer_answer(keys: str = Form(..., max_length=2000), text: str = Form(..., min_length=1, max_length=200), heard: str = Form("")):
    """Ana's answer to "do you want me to draft the email?" (button, typed or spoken)."""
    return assist.answer([k for k in keys.split(",") if k], text, heard or None)


@router.post("/mail/{tid}/send")
def send(tid: str, body: str = Form(..., max_length=4000)):
    if tid not in mail.THREADS:
        raise HTTPException(404, "no such email")
    try:
        return _view(mail.send(tid, body))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/mail/{tid}/reply")
async def reply(tid: str, text: str = Form(..., min_length=1, max_length=4000)):
    t = mail.THREADS.get(tid)
    if t is None or t["status"] == "draft":
        raise HTTPException(409, "send the email first")
    return _view(await run_in_threadpool(mail.reply, tid, text))
