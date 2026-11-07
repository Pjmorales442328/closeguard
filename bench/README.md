# bench — measured numbers for README, video and slides

Every figure quoted anywhere must be copied from `bench/results/latest.json` / `summary.md`, never typed by hand.
All data is synthetic (`data/synthetic`, seed 42). No network is needed: the model's answers replay from `agent/cache`.

## Run

```
python -m bench.run              # gate on  -> bench/results/latest.json + summary.md
python -m bench.run --gate off   # ablation -> bench/results/gate_off.json + summary_gate_off.md
python -m bench.run --live       # allow real calls on a cache miss (needs VULTR_INFERENCE_KEY); do not use for docs
python -m unittest tests.test_bench
```

## What each number means

- **Faults refused n/30**: planted faults (`faults.json`) the gate refused at all. **Refused with expected rule**: the rule
  that fired equals the label. A refusal by a different rule is still a refusal; it is listed under *Misses* with the reason.
- **False refusals**: legit lines (80 minus 30 faults) the gate refused. Precision/recall treat "fault line" as positive.
- **Gate OFF ablation**: with the gate removed, every proposal citing an invoice goes to the controller. The count is how
  many of those are planted faults. "Faults with no proposal" are faults neither matcher nor model proposed (they would
  show as unmatched rather than reach the controller).
- **Model cost**: calls, tokens and dollars for the calls this run replayed (3 proposals for the unmatched lines + 3 sample
  narratives, mirroring `agent/seed_run.py`). **Projected full close** multiplies the mean tokens per call by
  (unmatched + allowed) calls; it is labelled PROJECTION and is not a run.
- **Price**: Vultr's published Serverless Inference rate (URL + check date in the json). A glm-5.3-flash-specific rate
  could not be verified on vultr.com; the json says UNVERIFIED and shows a third-party low figure for comparison.
- **Time**: `deterministic_s` is matcher + gate only; `full_run_s` is the whole bench (cache replay included);
  `model_seconds_original` is the summed latency recorded when the cached calls were really made.
- **Human baseline**: always "estimate, not yet measured" (`bench/baseline.md`). The bench never produces it.
- **Attack set**: ~100 hostile strings in 9 classes (`bench/attacks.py`), each placed in the memo and in the reference of a
  gate-allowed proposal (2 trials per string). *Hard-blocked* = gate refused (`policy.memo_instruction`). *Flagged* = gate
  allowed but the approver must acknowledge the text (`policy.memo_unacknowledged` otherwise). *Passed unflagged* = gate
  allowed with no flag because it treats the text as data; a pass is a finding and is listed in full. The summary also
  shows the measured downstream controls (post without approval, self-approval, wrong role) that still refuse posting.
  **This set was used to tune the memo rule, so its block rate is coverage, not generalisation.** The blind held-out sets
  in `bench/heldout/` (set A, now seen; set B, run once at the end) are the honest numbers.

## Known limits

- One synthetic month, one model, memos in English plus a small multilingual attack list.
- `caught` is per-label; the gate stops at the first failing rule, so a line with two faults reports only one rule.
- Determinism covers everything except `timing` and `run_at` (test strips them before hashing).
- The attack bench exercises the gate path only; it does not send attacks to the model (that would need live calls).
- `bench/results/before.json` is the frozen pre-hardening run (16/198). Do not regenerate it; `summary.md` prints a
  before/after table when it exists. History: 16/198 (first word list) -> 198/198 (widened list, overfit to this set,
  11.8% false refusals on realistic memos) -> 158/198 hard-blocked + 40 flagged + 0 unflagged (two tiers, 0 false refusals).
