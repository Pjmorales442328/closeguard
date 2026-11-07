# bench/xcheck/report.py — `python -m bench.xcheck.report`: results.json -> results.md (agreement table, cost per close).
import json
from collections import Counter

from bench.cost import usd
from bench.xcheck.run import HERE


def load():
    return json.loads((HERE / "results.json").read_text("utf-8"))


def per_close(r: dict, reviews_per_close: int) -> dict:
    """PROJECTION: mean tokens/latency of the real review calls x the reviews one close would need."""
    live = [h for h in (r["trials"] + r["controls"] + r["narratives"]) if h.get("usage") and not h.get("cached")]
    n = len(live) or 1
    p = sum(h["usage"]["prompt"] for h in live) / n
    c = sum(h["usage"]["completion"] for h in live) / n
    lat = sum(h["latency_s"] for h in live) / n
    return {"label": "PROJECTION: mean per real review call x reviews per close; not a run", "calls": reviews_per_close,
            "mean_prompt": round(p), "mean_completion": round(c), "mean_latency_s": round(lat, 2),
            "usd": usd(round(p * reviews_per_close), round(c * reviews_per_close)),
            "usd_low": usd(round(p * reviews_per_close), round(c * reviews_per_close), lo=True),
            "seconds": round(lat * reviews_per_close, 1)}


def render(r: dict) -> str:
    m = r["cost"]["measured"]
    by = {}
    for t in r["trials"]:
        c = by.setdefault(t["cls"], Counter())
        c["reviewed"] += 1
        c["agree"] += t["agree"]
    pc = per_close(r, 1 + len(r["narratives"]))  # seed close: 1 model-proposed match (B0078) + 3 sample narratives
    lines = [
        "# Second-model cross-check (synthetic data, real calls)", "",
        f"First model `{r['first_model']}` proposed; second model `{r['second_model']}` reviewed from the evidence rows "
        "only (bank line, candidate invoices, the bare proposed inv_id/amount). It never saw the first model's "
        "explanation or confidence.", "",
        f"- Reviewed proposals: **{r['reviewed']}** (every non-unmatched proposal in bench/e2e; the other "
        f"{r['e2e_trials'] - r['reviewed']} injection trials produced no match, so there was nothing to review)",
        f"- Agree {r['agree']} / disagree {r['disagree']} -> agreement rate **{r['agreement_rate']}**",
        f"- Every reviewed proposal was already refused by the gate: {r['gate_refused_all_reviewed']}; "
        f"disagreements on a gate-ALLOWED proposal: **{r['disagreements_on_gate_allowed']}** (nothing the gate missed)",
        f"- Controls (clean memo): {sum(not c['agree'] for c in r['controls'])}/{len(r['controls'])} disagree",
        f"- Narratives: {sum(n['agree'] for n in r['narratives'])}/{len(r['narratives'])} judged accurate",
        f"- Real calls this run: {r['real_calls_this_run']}; tokens {m['prompt_tokens']} prompt / {m['completion_tokens']} "
        f"completion; model seconds {m['model_seconds_original']}; ${m['usd']} at the flat Vultr rate "
        f"(model price UNVERIFIED; low estimate ${m['usd_low']})", "",
        "| class | reviewed | agree | disagree |", "|---|---|---|---|",
        *[f"| {k} | {v['reviewed']} | {v['agree']} | {v['reviewed'] - v['agree']} |" for k, v in sorted(by.items())], "",
        f"## Added cost per close ({pc['label']})", "",
        f"{pc['calls']} review calls x ~{pc['mean_prompt']} prompt + ~{pc['mean_completion']} completion tokens, "
        f"~{pc['mean_latency_s']} s each -> **${pc['usd']}** (low ${pc['usd_low']}), ~{pc['seconds']} s per close.", "",
        "## Disagreement cases", "",
        *[f"- {t['id']} ({t['cls']}, {t['field']}): {t['reason']}" for t in r["trials"] if not t["agree"]], "",
        "Narratives:", *[f"- {n['txn_id']}: agree={n['agree']} - {n['reason']}" for n in r["narratives"]], "",
        "Honest reading: the only match the first model ever proposed on these lines is the B0078 partial payment "
        "(1250.00 against a 1520.00 invoice). The second model rejects it every time, for the right reason, and no "
        "injected memo changed that; but the gate had already refused it (policy.part_mismatch), so the cross-check "
        "added a second opinion, not a new catch.",
    ]
    return "\n".join(lines) + "\n"


def main():
    r = load()
    (HERE / "results.md").write_text(render(r), encoding="utf-8", newline="\n")
    print(render(r)[:600])


if __name__ == "__main__":
    main()
