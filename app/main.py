# app/main.py — FastAPI app factory: static files, routers. Run: uvicorn app.main:app --port 18080
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import bank_lock, desk, intake, ledger, ledger_export, mail, pages, app_view, runs, simple, stage, upload, voice
from app.services import stage_job


@asynccontextmanager
async def _life(_):
    stage_job.seed(stage._file)  # demo server starts with the normal bills scanned
    yield


app = FastAPI(title="Closeguard", docs_url=None, redoc_url=None, lifespan=_life)


@app.middleware("http")
async def _fresh_static(request, call_next):
    r = await call_next(request)
    if request.url.path.startswith("/static/"):
        r.headers["Cache-Control"] = "no-cache"  # browsers re-check (ETag), so a deploy reaches an open demo without Ctrl+F5
    return r

app.mount("/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static")
for r in (pages.router, runs.router, ledger.router, ledger_export.router, upload.router, intake.router, voice.router, desk.router, simple.router, stage.router, app_view.router, mail.router, bank_lock.router):
    app.include_router(r)
