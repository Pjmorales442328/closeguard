# bench/cost.py — model calls, tokens and dollar cost from the client's per-call history. Price source is cited, not assumed.
from statistics import mean

# Vultr's published Serverless Inference rate (flat, no per-model table found on docs.vultr.com on 2026-11-06).
PRICE = {
    "usd_per_m_input": 0.55,
    "usd_per_m_output": 2.75,
    "source": "https://docs.vultr.com/support/products/serverless/how-do-i-monitor-the-usage-and-cost-of-my-vultr-serverless-inference-subscription",
    "checked": "2026-11-06",
    "note": ("Vultr's doc states $0.55/M input and $2.75/M output for Serverless Inference without a per-model table; "
             "a glm-5.3-flash-specific rate could not be verified on vultr.com (pricing page blocks fetch), so the "
             "model-specific price is UNVERIFIED and this flat rate is used as the published figure. A third-party "
             "estimator (typingmind.com) lists $0.10/M in, $0.35/M out for glm-5.3-flash on Vultr; shown as 'low' only."),
    "low_usd_per_m_input": 0.10,
    "low_usd_per_m_output": 0.35,
}


def usd(prompt: int, completion: int, lo=False) -> float:
    pi = PRICE["low_usd_per_m_input" if lo else "usd_per_m_input"]
    po = PRICE["low_usd_per_m_output" if lo else "usd_per_m_output"]
    return round((prompt * pi + completion * po) / 1_000_000, 6)


def summarize(history: list, n_unmatched: int, n_allowed: int) -> dict:
    """Measured totals for the calls actually replayed, plus a labelled projection to a full close (all narratives)."""
    prompt = sum(h["usage"].get("prompt", 0) for h in history)
    completion = sum(h["usage"].get("completion", 0) for h in history)
    measured = {"calls": len(history), "cached": sum(1 for h in history if h.get("cached")),
                "prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion,
                "model_seconds_original": round(sum(h["latency_s"] for h in history), 3),
                "usd": usd(prompt, completion), "usd_low": usd(prompt, completion, lo=True),
                "models": sorted({h["model"] for h in history})}
    per_call = mean(h["usage"].get("prompt", 0) + h["usage"].get("completion", 0) for h in history) if history else 0
    calls = n_unmatched + n_allowed  # one propose per unmatched line + one narrative per allowed posting
    ptok = round(calls * per_call)
    share = prompt / (prompt + completion) if prompt + completion else 0
    projected = {"label": "PROJECTION: mean tokens per replayed call x (unmatched + allowed) calls; not a run",
                 "calls": calls, "total_tokens": ptok,
                 "usd": usd(round(ptok * share), round(ptok * (1 - share))),
                 "usd_low": usd(round(ptok * share), round(ptok * (1 - share)), lo=True)}
    return {"price": PRICE, "measured": measured, "projected_full_close": projected}
