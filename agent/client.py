# agent/client.py — the only module that talks to Vultr Serverless Inference: JSON mode, retries, disk cache.
import hashlib
import json
import os
import time
from pathlib import Path

BASE_URL = "https://api.vultrinference.com/v1"
MODEL = "glm-5.3-flash"
FALLBACK = "qwen3.8-27b"
CACHE_DIR = Path(__file__).resolve().parent / "cache"
MAX_TOKENS = 4000  # glm-5.3-flash reasons first; a small budget leaves content empty


class ModelError(RuntimeError):
    """Raised when no model attempt produced valid JSON. Callers treat it as 'no proposal'."""


def _openai_call(model: str, messages: list, max_tokens: int, timeout: float = 180) -> dict:
    """Real network call. Returns {"content": str, "usage": {prompt, completion}}. Key is read, never printed."""
    from openai import OpenAI  # imported lazily so tests with a fake call never need the SDK

    client = OpenAI(api_key=os.environ["VULTR_INFERENCE_KEY"],
                    base_url=os.environ.get("VULTR_INFERENCE_BASE_URL", BASE_URL), timeout=timeout, max_retries=0)
    r = client.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens,
                                       response_format={"type": "json_object"})
    u = r.usage
    return {"content": r.choices[0].message.content or "",
            "usage": {"prompt": getattr(u, "prompt_tokens", 0), "completion": getattr(u, "completion_tokens", 0)},
            "vultr": {"id": r.id, "created": r.created, "model": r.model, "fingerprint": r.system_fingerprint}}  # Vultr's own receipt


def cache_key(model: str, messages: list) -> str:
    return hashlib.sha256(json.dumps({"model": model, "messages": messages}, sort_keys=True).encode()).hexdigest()


class Client:
    """complete_json(messages) -> dict. `call` is injectable for tests: call(model, messages, max_tokens) -> dict."""

    def __init__(self, call=None, model=MODEL, fallback=FALLBACK, cache_dir=CACHE_DIR, max_tokens=MAX_TOKENS,
                 retries=3, backoff=2.0, read_cache=True):
        self.call = call or _openai_call
        self.models = [m for m in (model, fallback) if m]
        self.cache_dir = Path(cache_dir)
        self.max_tokens, self.retries, self.backoff = max_tokens, retries, backoff
        self.read_cache = read_cache  # False = live run: always call the model (answers still saved to cache_dir)
        self.last, self.history = {}, []  # per-call meta (model, latency_s, usage, cached) for reports/bench

    def _cache_path(self, model, messages):
        return self.cache_dir / f"{cache_key(model, messages)}.json"

    def _attempt(self, model, messages):
        t0 = time.monotonic()
        r = self.call(model, messages, self.max_tokens)
        latency = round(time.monotonic() - t0, 3)
        content = (r.get("content") or "").strip()
        if not content:
            raise ValueError("empty content")
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON is not an object")
        return data, {"model": model, "latency_s": latency, "usage": r.get("usage", {}), "content": content,
                      "vultr": r.get("vultr")}

    def complete_json(self, messages: list) -> dict:
        for model in self.models if self.read_cache else ():
            p = self._cache_path(model, messages)
            if p.exists():
                hit = json.loads(p.read_text("utf-8"))
                self.last = {**hit["meta"], "cached": True}
                self.history.append(self.last)
                return json.loads(hit["meta"]["content"])
        errors = []
        for model in self.models:
            for n in range(self.retries):
                try:
                    data, meta = self._attempt(model, messages)
                except Exception as e:  # noqa: BLE001 — network and parse errors alike
                    errors.append(f"{model} try {n + 1}: {e!r}"[:200])
                    time.sleep(self.backoff * n)
                    continue
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self._cache_path(model, messages).write_text(
                    json.dumps({"messages": messages, "meta": meta}, indent=1), encoding="utf-8", newline="\n")
                self.last = {**meta, "cached": False}
                self.history.append(self.last)
                return data
        raise ModelError("; ".join(errors))
