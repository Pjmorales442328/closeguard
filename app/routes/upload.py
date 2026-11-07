# app/routes/upload.py — judge CSV upload: bank + ledger through core.csvload's strict loader, memory only.
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app import config
from app.services import runs
from app.web import render
from core.csvload import MAX_BYTES, CsvError, parse_bank, parse_ledger

router = APIRouter()


async def _text(f: UploadFile, label: str) -> str:
    raw = await f.read(MAX_BYTES + 1)  # never read more than the cap
    if not raw:
        raise CsvError(f"{label}: no file or empty file")
    if len(raw) > MAX_BYTES:
        raise CsvError(f"{label}: file exceeds {MAX_BYTES // (1024 * 1024)} MB")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvError(f"{label}: not UTF-8 text") from None


@router.get("/upload")
def form(request: Request):
    return render(request, "upload.html", error=None)


@router.get("/upload/sample/{name}.csv")
def sample(name: str):
    path = {"bank": config.BANK_CSV, "ledger": config.LEDGER_CSV}.get(name)
    if path is None:
        raise HTTPException(404, "no such sample")
    return FileResponse(path, media_type="text/csv", filename=f"synthetic_{name}.csv")


@router.post("/upload")
async def upload(request: Request, bank: UploadFile = File(None), ledger: UploadFile = File(None)):
    try:
        if bank is None or ledger is None:
            raise CsvError("choose both a bank CSV and a ledger CSV")
        b = parse_bank(await _text(bank, "bank"))
        l = parse_ledger(await _text(ledger, "ledger"))
        if not b or not l:
            raise CsvError("both files need at least one data row")
    except CsvError as e:  # a clear 400 with the reason, never a 500
        return render(request, "upload.html", status_code=400, error=str(e))
    run = runs.create_run(b, l, uploaded=True)
    return RedirectResponse(f"/runs/{run.id}", status_code=303)
