# Invariants — what the code enforces, and the test that proves each

Run all of them: `.venv/Scripts/python -m unittest discover -s tests -t .` (127 OK on 2026-11-06; use the venv python, a plain python without FastAPI skips the app tests). Data is synthetic.

| # | Invariant | Enforced in | Proven by |
|---|---|---|---|
| 1 | **No model number becomes an amount.** A proposal's amount must equal the cited bank line; a changed amount is refused. | `core/gate.py` rule 2 | `tests/test_invariants.py::test_model_cannot_change_amount` |
| 2 | **A part must equal its invoice.** The model cannot short-pay an invoice even when the total matches the bank line. | `core/rules_parts.py` rule 11 | `tests/test_gate.py::PartMismatchTest::test_partial_payment_refused_even_when_amount_equals_bank` |
| 3 | **The gate is stdlib only.** Every module in `core/` imports only the Python standard library or `core`. | `core/*.py` | `tests/test_invariants.py::test_core_imports_stdlib_only` (AST parse, `sys.stdlib_module_names`) |
| 4 | **Fail closed.** A missing/garbled field, or any exception inside a rule, returns a refusal, never an allow. | `core/gate.py` `_closed`, `core/sod.py` | `tests/test_invariants.py::test_fail_closed_missing_field`, `::test_fail_closed_on_exception`; `tests/test_memo.py::test_fail_closed_on_bad_type` |
| 5 | **Proposer ≠ approver; only controller/CFO approve.** | `core/sod.py` rule 13 | `tests/test_invariants.py::test_segregation_of_duties`; `tests/test_app.py::test_agent_approval_refused` |
| 6 | **No post without a valid approval.** | `core/sod.py` rule 14, `writer/db.py` | `tests/test_invariants.py::test_unapproved_post`; `tests/test_writer.py::test_unapproved_post_refused_and_nothing_written` |
| 7 | **A gate refusal cannot be approved.** | `app/services/approvals.py` | `tests/test_app.py::test_gate_refusal_cannot_be_approved` |
| 8 | **A flagged memo needs a ticked acknowledgement before approval.** | `core/rules_memo_flag.py` + `core/sod.py` (`policy.memo_unacknowledged`) | `tests/test_memo.py::test_flag_requires_acknowledgement`; `tests/test_app.py::test_flagged_line_needs_acknowledgement` |
| 9 | **Memo text never changes numbers.** Memo rules only refuse or flag; amount, invoices and parts are untouched. | `core/rules_memo.py`, `core/rules_memo_flag.py` | `tests/test_memo.py::test_numbers_untouched`; `tests/test_agent.py::test_memo_injection_is_data_and_cannot_widen_schema` |
| 10 | **All 30 planted faults are refused with the expected rule, and 0 legitimate lines are refused.** | gate rules 1–12 | `tests/test_gate.py::test_all_30_faults_refused_with_expected_rule`, `::test_zero_false_refusals_on_legit_lines` |
| 11 | **Over-cap needs a CFO.** | `core/gate.py` rule 7 | `tests/test_invariants.py::test_over_cap_lifted_by_cfo` |
| 12 | **Journal is append-only for every role.** UPDATE/DELETE/TRUNCATE are blocked by trigger; the reader cannot insert. | `writer/schema.sql` | `tests/test_writer.py::test_update_delete_refused_for_both_roles`, `::test_reader_cannot_insert` |
| 13 | **Posting is verified by a second path.** The read-only role reads back what the writer wrote; tampering (even by a superuser) is detected by hash recompute. | `writer/verify.py` | `tests/test_writer.py::test_reader_sees_writer_rows`, `::test_superuser_tamper_detected` |
| 14 | **The audit chain reports the first tampered entry.** | `core/chain.py` | `tests/test_chain.py` (5 tests); `tests/test_app.py::test_tamper_detected_and_real_chain_untouched` |
| 15 | **The public "posted without approval" counter is computed from stored attempts, not typed.** | `app/services/attempts.py` | `tests/test_app.py::test_counter_is_computed_not_typed` |
| 16 | **Uploaded judge CSVs never reach Postgres.** | `app/routes/upload.py` | `tests/test_app_upload.py::test_uploaded_run_never_uses_writer_db` |
| 17 | **The demo replays real model answers offline**, no network or key needed. | `agent/client.py` cache | `tests/test_integration.py::test_seed_run_replays_cache_without_network_or_key`; `tests/test_agent.py::test_committed_seed_cache_replays_without_network` |

## Not enforced (claimed nowhere)

- **Agent has no database credentials at process level.** The model client code never reads `CG_*` DSNs, but the agent runs in the same container as the writer. No test proves isolation.
- **Writer re-checks the memo acknowledgement.** It does not; the check happens in `core.sod` before `writer/db.py` is called.
- **Every gate refusal is chained.** The app logs each gate decision (`app/services/runs.py`, `state.log("gate_decision", ...)`), but no test asserts it.
- **The memo rule catches injections in general.** Blind set B: 44% passed unflagged (`bench/heldout/set_b/results.md`).
