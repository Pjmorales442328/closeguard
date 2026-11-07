# app/routes/desk.py — Guard Desk page, scan (camera frame, photo or sample bill) and sample images.
import re

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from agent import extract
from app.services import desk, intake
from app.web import render

router = APIRouter()


def _page(request, v=None, error=None, status_code=200):
    """JS posts with X-Desk and gets just the result fragment; a plain form post gets the whole desk page."""
    if request.headers.get("X-Desk"):
        return render(request, "partials/desk_result.html", status_code=status_code, v=v, error=error, names=extract.MODELS)
    return render(request, "desk.html", status_code=status_code, run=desk.latest_run(), samples=desk.SAMPLES, voice=None, v=v, error=error, names=extract.MODELS)


@router.get("/desk")
def page(request: Request):
    return _page(request)


@router.get("/desk/sample/{name}")
def sample(name: str):
    if name not in desk.SAMPLES:
        raise HTTPException(404, "no such sample")
    return FileResponse(intake.BILLS_DIR / f"{name}.jpg", media_type="image/jpeg")


@router.post("/desk/scan")
async def scan(request: Request, files: UploadFile = File(None), sample: str = Form("")):
    try:
        if sample:
            if not re.fullmatch(r"B\d\d", sample) or sample not in desk.SAMPLES:
                raise intake.IntakeRefused("unknown sample bill")
            name, data = f"{sample}.jpg", (intake.BILLS_DIR / f"{sample}.jpg").read_bytes()
        elif files is not None:
            name, data = files.filename or "scan", await files.read(intake.MAX_BYTES + 1)
        else:
            raise intake.IntakeRefused("no image sent")
        if len(data) > intake.MAX_BYTES:
            return _page(request, error="That image is larger than 4 MB.", status_code=413)
        v = await run_in_threadpool(desk.scan, name, data)  # model reads must not hold the event loop
    except intake.IntakeRefused as e:
        return _page(request, error=str(e), status_code=415)
    return _page(request, v)
