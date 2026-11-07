# Held-out memo-rule test (blind)

Datasets `attacks.json` (85 hostile strings, 12 classes) and `legit.json` (85 realistic bank-line memos) were written
and committed (40c58e6) **before** reading `core/rules_memo.py` or `bench/attacks.py`. Synthetic.
Caveat: one note about the rule (CJK/Cyrillic handling) was known before writing.

Run: `python -m bench.heldout.run` -> `results.json`, `results.md` (every pass and every false refusal listed).

## Result, single-tier rule (run 2026-11-06 morning, base proposal B0002) — the blind run
- Attacks: 96/165 trials blocked (58.2%). Strong on homoglyph (16/16), markup, keyword-y multilingual; weak on
  amount_prose (0/14), multistep (4/14), subtle (4/16), paraphrase (8/16).
- Legit: 20/170 trials refused (11.8%); 10/85 memos refused. Offending terms: `approve`/`approval` (4 memos),
  `partial payment`, `discount`, `credit note`, `authoris` (Pre-authorised debit), `overrid`, `ignor`.
  The first seven are everyday bank-line text, so this is not an artefact of the test set.

## Result, two-tier rule (run 2026-11-06, same base proposal) — set A is NO LONGER blind
The memo rule was then split into HARD (refuse: markup, role prefixes, override phrases aimed at the
checker, encoded/obfuscated text) and SOFT (allow but flag; the approver must tick an acknowledgement or the approval is
refused with `policy.memo_unacknowledged`). **This set A was used to develop that split**, so the numbers below are
coverage of a seen set, not generalisation. Set B (`set_b/`, written separately without seeing the rule) is the honest test and is run
once.
- Attacks: 147/165 hard-blocked (89.1%), 18 flagged for the approver, **0 passed unflagged**. Flag-only classes:
  amount_prose 6, subtle 6, fake_notice 2, multistep 2, split 2 (the split pair is scanned per field, so "ignore the" +
  "rules and approve" is not joined).
- Legit: 0/170 refused, 24 flagged (12/85 memos: approved/approval ×4, partial payment, discount, credit note, credit
  memo, Pre-authorised, Intercompany, Override fee, Ignore duplicate), 146 clean.

## Honest read
On real data the memo rule is a tripwire plus a flag, not a control. The hard tier only fires on things no real bank
memo contains (tags, `SYSTEM:`, "ignore the rules", base64). Everything that merely sounds like approval or amount talk is
allowed as data and shown amber to the approver, who must acknowledge it. The real protection is structural: the gate
checks amount against the bank line, invoices against the ledger, caps, and posting needs a controller/CFO approval, so a
memo that passes still cannot change the amount or post.

## Remaining weaknesses
1. Phrase lists are finite: a paraphrase that avoids every verb/object pair and every finance word passes unflagged.
2. Split attacks across memo and reference are scanned per field; a phrase cut in two is at best flagged.
3. Non-English coverage is a handful of verb/object pairs per language; other languages pass or are only flagged.
4. The flag is a checkbox: a careless approver can tick it without reading. SoD still needs a second person.
5. Set A is seen. Only set B (and future fresh sets) can say how the split generalises.
