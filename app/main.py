# app/main.py — FastAPI app factory: static files, routers. Run: uvicorn app.main:app --port 18080
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import desk, intake, ledger, ledger_export, mail, pages, app_view, runs, simple, stage, upload, voice

app = FastAPI(title="Closeguard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static")
for r in (pages.router, runs.router, ledger.router, ledger_export.router, upload.router, intake.router, voice.router, desk.router, simple.router, stage.router, app_view.router, mail.router):
    app.include_router(r)
