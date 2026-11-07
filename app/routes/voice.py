# app/routes/voice.py — push-to-talk transcript (logs nothing), confirmed question -> answer (one chain event), audio.
import re

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app import config
from app.routes import runs as runs_routes
from app.services import desk, voice
from app.web import is_htmx, render
from agent import voice as av

router = APIRouter()
MAX_AUDIO = 1024 * 1024
MAGIC = ((b"\x1a\x45\xdf\xa3", 0, "audio/webm"), (b"RIFF", 0, "audio/wav"), (b"ftyp", 4, "audio/mp4"), (b"OggS", 0, "audio/ogg"))


def _sniff(raw: bytes):
    return next((m for sig, off, m in MAGIC if raw[off:off + len(sig)] == sig), None)


def _card(request, run, v):
    """htmx swaps just the card; a plain form post gets the whole run page with the card filled in."""
    if is_htmx(request):
        return render(request, "partials/voice.html", run=run, voice=v)
    return runs_routes._body(request, run, voice=v)


@router.post("/runs/{run_id}/voice/transcribe")
async def transcribe(request: Request, run_id: str, audio: UploadFile = File(...), bill: str = Form("")):
    run = runs_routes._run(run_id)
    raw = await audio.read(MAX_AUDIO + 1)
    if len(raw) > MAX_AUDIO:
        raise HTTPException(413, "recording too large: hold the button for at most 15 seconds")
    mime = _sniff(raw)
    if not mime:
        raise HTTPException(415, "unsupported audio format: type your question instead")
    if not config.model_live():
        return _card(request, run, {"hint": "Voice input is off on this server. Type your question instead.", "bill": bill})
    if not voice.take():
        return _card(request, run, {"hint": "Voice budget used up this hour. Type your question instead.", "bill": bill})
    try:
        heard = await run_in_threadpool(av.transcribe, raw, mime)  # network call off the event loop
    except Exception:  # noqa: BLE001 — network or model error: the text path still works
        return _card(request, run, {"hint": "I could not transcribe that. Type your question instead.", "bill": bill})
    return _card(request, run, {"text": heard[:300], "heard": heard[:300], "bill": bill})  # nothing is answered or logged yet


@router.post("/runs/{run_id}/voice/ask")
def ask(request: Request, run_id: str, text: str = Form(""), heard: str = Form(""), bill: str = Form("")):
    run = runs_routes._run(run_id)
    if not text.strip():
        return _card(request, run, {"hint": "Type or record a question first.", "bill": bill})
    a = voice.answer(run, text, heard or None, desk.lookup(bill) if bill else None)
    return _card(request, run, {"text": text[:300], "bill": bill, **a})


@router.get("/voice/audio/{key}")
def audio(key: str):
    if not re.fullmatch(r"[0-9a-f]{32}", key):
        raise HTTPException(404, "no such audio")
    try:
        p = voice.audio(key)
    except Exception:  # noqa: BLE001 — TTS failed: the page falls back to the browser voice
        p = None
    if not p:
        raise HTTPException(404, "no audio; the page uses the browser voice")
    return FileResponse(p, media_type="audio/mpeg" if p.suffix == ".mp3" else "audio/wav")
