# E4.5 — Write from a verified per-part source handoff

## Change

E4.4's full-page selection/answer experiment abstained on all seven question parts. This stage
separates those responsibilities: reuse its explicitly AI-reviewed source selections and give
the E4.3 structured Writer only the small set of verified extracts grouped by question part.
This is an **assisted evaluation**, not a production research change or automatic retrieval score.

`evals.reports_acceptance.handoff_writer` binds both cases to the published E4.4 artifact hashes,
checks the review's input/coverage bindings, reproduces its offline diagnosis, and revalidates
literal quotations and official hosts before admitting any model call. Reviewer notes, previous
model answers, answer keys and evaluator-only pages are not passed to Writer.

Each quote gets a stable ID bound to its question part. The unchanged E4.3 `StructuredWriter`
schema and system instruction produce assertions referencing these IDs. The backend rejects
unknown links, foreign inline citations and assertions mixing quotes from different parts.
Every required part remains in the final checked document: a part with no linked assertion is
marked as a reviewed evidence gap or Writer omission. Model-proposed free-text unanswered topics
remain diagnostic data rather than factual delivery text.

These are structural guarantees only. A valid same-part link may still misstate the source or
fail to answer the part sufficiently; semantic support stays `pending_review`. A regression test
preserves this distinction using a well-linked but unsupported platform-exclusivity statement.

## Reproduction

```powershell
# Default: verify the handoff and write per-part templates; no model call.
.venv\Scripts\python.exe -m evals.reports_acceptance.handoff_writer evals/results/question_coverage_20261027T065145Z_2030685ed2

# Explicit opt-in: two assisted Writer calls, no search or page fetch.
.venv\Scripts\python.exe -m evals.reports_acceptance.handoff_writer evals/results/question_coverage_20261027T065145Z_2030685ed2 --execute
```

The run requires the private saved E4.4 inputs/review artifacts; public metadata alone cannot
reconstruct source content. Provider retries are disabled, each call has a 90-second timeout,
and failures/parse errors are retained without retries for success. No production defaults change.

## Observed results

Run `handoff_writer_20261028T024948Z_2ec2081068`, qwen-flash:

| Task | Linked candidate parts | Explicit unresolved parts | Rejected assertions | AI task assessment |
| --- | ---: | ---: | ---: | --- |
| Python 3.13.0 | 2 | 1 | 0 | Partial |
| PostgreSQL 17.0 | 3 | 1 | 0 | Partial |

Total: **2 logical model calls, 0 searches, 0 fetched pages**, 1,421 input tokens and 480 output
tokens. Input hashes and source fingerprint remain unchanged during execution.

The five provisionally supported parts now have linked candidates. The Python output describes
the date, experimental state and installer availability without adding platform exclusivity.
Its installation-choice part remains explicitly unresolved even though the model again returns
an empty unanswered-topic list. The backend's exhaustive part accounting prevents that omission
from hiding the evidence gap.

The PostgreSQL output answers date, JSON_TABLE and basic `pg_basebackup` incremental capability
using the saved official release-page excerpts, including the sentence recovered during E4.4
offline review. It neither supplies a complete backup/restore procedure nor invents utility
details. `pg_combinebackup` remains unresolved.

AI initial review covers all six assertion entries as nine factual units, verifying literal
assertion/source spans and hashes. The units appear supported within the supplied release-page
context, but one Python entry still combines several facts. Both full tasks remain partial.
Human accuracy and Claim-support metrics remain null; no trusted Judge score is generated.

Compared with E4.4's blanket abstention, input selection, input size/shape and output schema all
change. The Writer system instruction matches E4.3, but the present result cannot isolate the
cause of E4.4's failure. It also cannot establish automatic research performance: an AI reviewer
selected the evidence and declared two gaps. These are two exposed development tasks with one
sample each, without a new task group or a general accuracy/latency claim.

## Verification and next work

Full regression: **531 passed, 6 skipped**. Eight new tests cover per-part accounting, mixed/unknown
links, structural/semantic limits, review reproduction and note isolation, corruption checks before
model admission, default offline behavior, and bounded calls retaining parse failure. Changed
Python files pass Ruff lint/format; `git diff --check` passes. A real default CLI smoke run verifies
offline template generation without model calls.

The [content-free result record](../../evals/reports/e4-5-handoff-writer-2026-10-28.json) stores
manifests, counts, hashes and provisional assessments. Exact inputs, assertions, candidate reports
and `AI_REVIEW.json`/`AI_REVIEW.md` stay ignored in the private run directory.

The assisted source-to-Writer boundary is now exercised. Next freeze a small new development
task group before changing this prompt again. Evaluate source selection and writing separately,
preserve known/unknown parts, and include at least one missing-evidence case. Keep production
adoption gated on that broader check; do not turn assisted selection into an end-to-end score or
silently fetch missing evaluator reference passages to complete these two reports.
