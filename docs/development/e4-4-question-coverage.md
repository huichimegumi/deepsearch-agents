# E4.4 — Question slots and source-gap diagnosis

## Implemented

The E4.3 next step is now implemented as an evaluation-only coverage runner and offline review
library. The original frozen questions/answer keys are unchanged. Question-only decomposition
defines three Python parts (date, experimental state, installation choice) and four PostgreSQL
parts (date, JSON_TABLE, incremental backup, pg_combinebackup).

Every required part appears in the checked output. Missing/duplicate parts become unresolved;
unknown parts cannot replace required ones. A candidate needs nonempty text and exact contiguous
quotes from actual saved official fetched-page Evidence. Unknown/altered quotes, inconsistent
unresolved payloads and foreign inline citations fail closed. Rendered unresolved parts say only
that this run produced no checked candidate, never that the information does not exist.

As before, exact quote checks establish provenance only. Structurally accepted candidates retain
`semantic_support=pending_review`. No production route or Writer default changes.

```powershell
# Verify saved inputs and produce a seven-part offline template; no model calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.coverage evals/results/extractive_compression_20261027T062414Z_925eced641

# Explicit experiment: one call per case, no retrieval, no retries for success.
.venv\Scripts\python.exe -m evals.reports_acceptance.coverage evals/results/extractive_compression_20261027T062414Z_925eced641 --execute
```

Before model admission, the inherited E4.3 preflight validates both cases' saved input/quote hashes
and frozen questions. Generation receives question parts and full bounded official Evidence from
the saved E4.2 inputs. It does not receive answer keys, evaluator reference pages, prior generated
answers or the later AI review. This jointly changes input size and structured task shape from
E4.3; it is not an isolated Writer prompt comparison.

## Live experiment: retain the failure

Run `question_coverage_20261027T065145Z_2030685ed2` uses qwen-flash, provider retries disabled,
90 seconds per call: **2 logical calls, 0 searches, 0 fetched pages**, 3,937 input tokens and
194 output tokens. Source/input hashes remain unchanged during the pilot.

Both outputs parse and enumerate every part, but the model marks **all seven unresolved**,
including dates and feature descriptions already supported by the supplied text. There are
**zero candidate answers**. This is a failed generation experiment, not improved coverage or a
successful abstention score. No retry was made to obtain a better-looking result. The underlying
cause of this blanket abstention has not been isolated.

## Offline source review and repair handoff

`coverage_review.diagnose_review` accepts exactly one explicit review entry per part, rechecks
each reviewed quote against that case's saved records, and compares source spans with the prior
selected extracts. It preserves original model statuses and counts. Reviewer sufficiency
judgements remain provisional AI annotations, not deterministic semantic checks or human scores.

| Part | Offline AI diagnosis | Current model result |
| --- | --- | --- |
| Python date | Selected supporting extract not used | Unresolved |
| Python experimental state | Selected supporting extract not used | Unresolved |
| Python installation choice | Insufficient support identified in bounded saved material | Unresolved |
| PostgreSQL date | Selected supporting extract not used | Unresolved |
| PostgreSQL JSON_TABLE | Selected supporting extract not used | Unresolved |
| PostgreSQL incremental backup | Supporting official passage omitted by prior selection | Unresolved |
| PostgreSQL pg_combinebackup | Insufficient support in bounded saved material | Unresolved |

The reviewed handoff recovers the basic incremental-backup capability sentence directly from the
actual saved official release-page record. It does not infer a full backup/restore procedure or
reuse pgEdge as an official source. The utility name is absent from the actual bounded official
input; no evaluator-only announcement is injected. For Python, installer availability and
experimental status do not by themselves establish the optional-build installation choice;
the mimalloc optional/default statement still describes the allocator.

The library emits a reusable per-part source handoff and Markdown containing original quotes for
five provisionally supported parts, with explicit evidence requests for the other two. This is
**offline source-review output**, not a successful model-generated report. Four supported-part
misses, one selection gap and two insufficient-input assessments are kept separate from the
model's zero candidates. No coverage/accuracy percentage is inferred from these AI judgements.

Private `source_review.json` binds the review to input/coverage hashes; `diagnostics.json` and
`reviewed_handoff.md` retain verified quotations and explicit unresolved parts. The original model
`coverage.json`, candidate and counts remain unchanged. `AI_REVIEW.json` records the review scope.

## Verification and provenance

Full regression: **523 passed, 6 skipped**. Seventeen new tests cover exhaustive accounting,
duplicates/unknown parts, invalid sources, inconsistent unresolved output, link/semantic limits,
offline operation, bounded calls/parse failure, and reviewed recovery without relabeling model
failure. Changed Python files pass Ruff lint/format; `git diff --check` passes.

The offline review module was added after the live pilot failed. Removing only that later-added
module from the final source-hash map exactly reconstructs the pilot fingerprint. The
[content-free result record](../../evals/reports/e4-4-question-coverage-2026-10-27.json) preserves
both fingerprints, the later module hash, input/output/review hashes and failed model outcomes.
Final-source tests include the review library; no final-source live rerun is claimed. Raw reports
and source text remain ignored under `evals/results/`. Human accuracy and coverage remain null.

## Next step

Keep this full-page selection/answer experiment disabled. Reuse the verified source handoff to
separate source selection from writing: supply explicit per-part extracts to the previously
working structured Writer, preserving unresolved installation/utility details. Then add a small
new task group before considering production adoption. Do not keep revising negative-assertion
keywords or rerun these same two questions until they pass. Any later targeted official utility
page fetch must be a separate retrieval experiment with its own recorded budget.
