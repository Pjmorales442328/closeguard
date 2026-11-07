# app/routes/bank_lock.py — Maria lifts a bank-change lock on a supplier after calling them back (PIN, chained).
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.services import bank_lock, runs, signin

router = APIRouter()
WHO = "Maria"  # the demo's named approver, same as the pay screen


@router.post("/simple/pay/{rid}/callback")
async def callback(request: Request, rid: str):
    """Maria lifts a bank-change lock after calling the supplier on the number on file. Needs her PIN; chained."""
    form = await request.form()
    if runs.get_run(rid) is None:
        raise HTTPException(404, "run not found")
    supplier = str(form.get("supplier", ""))[:120]
    if form.get("called") != "yes":
        return RedirectResponse(f"/simple/pay/{rid}?err={quote('Tick the box once you have called them.')}", status_code=303)
    if err := signin.check(WHO, form.get("pin", ""), f"lift the bank-change lock on {supplier}"):
        return RedirectResponse(f"/simple/pay/{rid}?err={quote(err)}", status_code=303)
    if not bank_lock.call_back(supplier, WHO):
        return RedirectResponse(f"/simple/pay/{rid}?err={quote('That supplier is not locked.')}", status_code=303)
    return RedirectResponse(f"/simple/pay/{rid}?note=called-back", status_code=303)
