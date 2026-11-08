# app/routes/stage.py — 3D scan room: pick or photograph a bill, the real server reads and checks it step by step, then talk.
import json
import re

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from agent import voice as av
from app import config, state
from app.routes import voice as voice_routes
from app.services import app_bank, bank_import, bill_remove, intake, mail, stage_job, stage_log, stage_voice, voice
from app.web import render

router = APIRouter()
MAX_AUDIO = voice_routes.MAX_AUDIO
EXPECT = {"clean": (True, "good bill"), "line_sum": (False, "lines do not add up to the total"),
          "duplicate_invoice": (False, "same invoice number as B02 (scan B02 first)"), "unknown_supplier": (False, "supplier not on the list"),
          "instruction": (True, "hidden 'approve me' text; must be read as a normal bill"), "scan": (True, "poor scan; must still read right"),
          "dates": (False, "due date before invoice date"), "ambiguous": (False, "hard to read: readers may disagree")}
SAMPLES = {m["file"][:3]: (m["truth"]["supplier"], m["truth"]["total"], *EXPECT[m["trap"]])
           for m in json.loads((intake.BILLS_DIR / "manifest.json").read_text("utf-8"))["bills"]}
PHOTOS = config.ROOT / "data" / "synthetic" / "photos"  # photo receipts (AI-generated, fictional): the demo set
SAMPLES |= {m["id"]: (m["supplier"], m["total"], m["good"], m["why"])
            for m in json.loads((PHOTOS / "manifest.json").read_text("utf-8"))["receipts"]}
SHOWN = [k for k in SAMPLES if k.startswith("R")] + ["B13"]  # B13: the smudged bill where the two readers can disagree
LATER = {"R06", "R09", "B09"}  # pass the scan; caught later at the bank match or payment


def _file(name: str):
    return (PHOTOS if name.startswith("R") else intake.BILLS_DIR) / f"{name}.jpg"


@router.get("/stage")
def page(request: Request):
    return render(request, "stage.html", samples={k: SAMPLES[k] for k in SHOWN}, later=LATER, n=len(stage_job.SCANNED), seq=len(state.CHAIN), live=config.model_live())


@router.get("/stage/sample/{name}")
def sample(name: str):
    if name not in SAMPLES:
        raise HTTPException(404, "no such sample")
    return FileResponse(_file(name), media_type="image/jpeg")


@router.post("/stage/scan")
async def scan(files: UploadFile = File(None), sample: str = Form("")):
    """Starts the real read in the background and returns at once; the page follows /stage/job/{id} step by step."""
    if sample:
        if sample not in SAMPLES or not re.fullmatch(r"[BR]\d\d", sample):
            return JSONResponse({"error": "unknown sample bill"}, status_code=415)
        name, data, real = f"{sample}.jpg", _file(sample).read_bytes(), False
    elif files is not None:
        name, data, real = files.filename or "photo", await files.read(intake.MAX_BYTES + 1), True
    else:
        return JSONResponse({"error": "no image sent"}, status_code=415)
    if len(data) > intake.MAX_BYTES:
        return JSONResponse({"error": "that image is larger than 4 MB"}, status_code=413)
    return {"job": stage_job.start(name, data, real)}


@router.get("/stage/job/{jid}")
def job(jid: str):
    j = stage_job.JOBS.get(jid)
    if j is None:
        raise HTTPException(404, "no such scan")
    return {"steps": j["steps"], "done": j["done"], "v": j["v"]}


@router.get("/stage/latest")
def latest():
    """The newest scan job, from any screen: the app's Behind the scenes panel follows it."""
    return {"job": stage_job.LATEST["job"]}


@router.get("/stage/log")
def log(after: int = 0):
    return stage_log.since(after)


@router.post("/stage/clear")
def clear():
    stage_job.clear()
    app_bank.LAST_RUN["id"] = None
    mail.clear()
    bill_remove.clear()
    bank_import.clear()  # the demo month starts again with "import the bank statement"
    stage_job.seed(_file)  # demo server: the normal bills come back, so the app is never empty
    return RedirectResponse("/stage", status_code=303)


@router.post("/stage/answer")
def answer(bill: str = Form(...), text: str = Form(""), heard: str = Form("")):
    return stage_voice.answer(bill, text, heard or None)


@router.post("/stage/confirm")
def confirm(bill: str = Form(...)):
    return stage_voice.confirm(bill)


@router.post("/stage/run")
async def run():
    """The scanned bills that passed (or were confirmed) become the ledger; the real matcher + gate run on the server."""
    if not stage_job.SCANNED:
        raise HTTPException(400, "scan at least one bill first")
    r = await run_in_threadpool(app_bank.rematch)
    if r is None:
        return JSONResponse({"error": "no bill is ready or confirmed yet"}, status_code=400)
    return {"run": r.id, "url": f"/simple/pay/{r.id}", "allowed": r.counters()["allowed"], "held": r.counters()["refused"]}


@router.post("/stage/hear")
async def hear(audio: UploadFile = File(...)):
    """Ana's push-to-talk -> Vultr Whisper transcript. Nothing is acted on: she sees and edits it, then presses Send."""
    raw = await audio.read(MAX_AUDIO + 1)
    mime = voice_routes._sniff(raw)
    if len(raw) > MAX_AUDIO or not mime:
        return JSONResponse({"error": "recording too long or not audio; type the answer instead"}, status_code=415)
    if not config.model_live() or not voice.take():
        return JSONResponse({"error": "voice input is off on this server; type the answer instead"}, status_code=503)
    try:
        return {"heard": (await run_in_threadpool(av.transcribe, raw, mime))[:200]}
    except Exception:  # noqa: BLE001 — network/model error: typing still works
        return JSONResponse({"error": "could not transcribe that; type the answer instead"}, status_code=502)
