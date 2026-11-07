# agent/seed_voice.py — one-off: speak the 3 demo answers via Vultr TTS and commit them under app/static/voice/ (3 real calls).
# Run: CG_ENV_FILE=D:/closeguard/.env python -m agent.seed_voice   (the key is loaded by code and never printed)
import os
import time
from pathlib import Path

QUESTIONS = ("Why was B0078 refused?", "What is left to approve?", "Give me the close summary")


def load_key() -> None:
    for line in Path(os.environ["CG_ENV_FILE"]).read_text("utf-8").splitlines():
        if line.startswith(("VULTR_INFERENCE_KEY=", "VULTR_INFERENCE_BASE_URL=")):
            k, v = line.split("=", 1)
            os.environ[k] = v.strip().strip('"')


def main() -> None:
    from agent import voice as av
    from app.services import runs, voice as sv

    load_key()
    run = runs.create_seed_run()  # offline run: the answers below are exactly what the page speaks at first load
    sv.DEMO_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "mp3"
    for q in QUESTIONS:
        a = sv.answer(run, q)
        t0 = time.monotonic()
        data = av.speak(a["answer"], fmt)
        if fmt == "mp3" and not data.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3")):
            fmt, data = "wav", av.speak(a["answer"], "wav")  # server ignored mp3: keep wav for all
        (sv.DEMO_DIR / f"{a['key']}.{fmt}").write_bytes(data)
        print(f"{q!r}: {len(data)} bytes {fmt}, {time.monotonic() - t0:.1f} s")


if __name__ == "__main__":
    main()
