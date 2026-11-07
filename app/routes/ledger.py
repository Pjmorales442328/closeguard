# app/routes/ledger.py — audit chain viewer, verify, and tamper demo (JSON for curl, partial for htmx).
from fastapi import APIRouter, Form, Request

from app import state
from app.services import ledger
from app.web import is_htmx, render

router = APIRouter()


@router.get("/ledger")
def view(request: Request):
    with state.LOCK:
        entries = list(reversed(state.CHAIN))
    return render(request, "ledger.html", entries=entries, check=ledger.verify())


@router.get("/ledger/verify")
def verify(request: Request):
    res = ledger.verify()
    return render(request, "partials/verify.html", v={**res, "head": ledger.head()}) if is_htmx(request) else res


@router.post("/ledger/tamper-demo")
def tamper(request: Request, seq: int | None = Form(None)):
    res = ledger.tamper_demo(seq)
    return render(request, "partials/tamper.html", t=res) if is_htmx(request) else res
