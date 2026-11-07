# app/services/recorder.py — per-run model client with a hard budget (calls + wall time) on BOTH the live and cache-first paths.
import json
import time
from functools import partial

from app import config

MAX_LIVE_CALLS = 10  # network calls per run, whatever the path; cached answers are free
LIVE_BUDGET_S = 90  # wall budget for network calls per run; each call's timeout is cut to what is left
LIVE_TIMEOUT_S = 60
BUDGET_NOTE = f"AI limit for this run reached ({MAX_LIVE_CALLS} questions or {LIVE_BUDGET_S} s)"


def _offline(*_a, **_k):
    raise ConnectionError("cache only: no network on this path")


class Recorder:
    """complete_json per bank line. live=True: network first, cache on failure. live=False: cache first, network only on a
    cache miss and only while the budget lasts; past it the line raises ModelError and stays unmatched. One row per call."""

    def __init__(self, live: bool):
        from agent.client import CACHE_DIR, Client, _openai_call
        self._call = _openai_call
        self.live = live
        self.net = Client(call=_offline, fallback=None, retries=1, backoff=0, read_cache=False,
                          cache_dir=config.runtime_cache() if live else CACHE_DIR)
        self.cache = Client(call=_offline, retries=1, backoff=0)  # committed agent/cache, never the network
        self.deadline, self.n_net, self.calls = time.monotonic() + LIVE_BUDGET_S, 0, []

    def _budget_left(self) -> float:
        left = self.deadline - time.monotonic()
        return left if left > 1 and self.n_net < MAX_LIVE_CALLS else 0

    def complete_json(self, messages: list) -> dict:
        from agent.client import ModelError
        txn = json.loads(messages[-1]["content"])["bank_line"]["txn_id"]
        if not self.live:
            try:
                return self._note(txn, "cached", self.cache, self.cache.complete_json(messages))
            except ModelError:
                pass  # cache miss: try the network if the budget allows
        left, failed = self._budget_left(), None
        if left:
            self.n_net += 1
            self.net.call = partial(self._call, timeout=min(LIVE_TIMEOUT_S, left))
            try:
                return self._note(txn, "live", self.net, self.net.complete_json(messages))
            except ModelError as e:
                failed = str(e)[:160]
        else:
            failed = BUDGET_NOTE
        if self.live:
            try:
                return self._note(txn, "fallback", self.cache, self.cache.complete_json(messages), failed)
            except ModelError:
                pass
        self.calls.append({"txn": txn, "how": "skipped" if not left else "failed", "error": failed, "latency_s": 0, "tokens": 0})
        raise ModelError(failed)

    def _note(self, txn, how, client, data, error=None):
        h = client.history[-1]
        u = h.get("usage") or {}
        self.calls.append({"txn": txn, "how": how, "latency_s": h.get("latency_s", 0), "error": error,
                           "tokens": int(u.get("prompt", 0) or 0) + int(u.get("completion", 0) or 0)})
        return data
