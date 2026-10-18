# E3.1: real local reports and evidence review packages

The next milestone moves from retrieved passages to actual report generation. The new
`evals.reports_acceptance.run` entry point executes six fixed development tasks through the
production workflow: four single-document tasks, a monetary-policy/investment-outlook combination,
and a no-answer task. References come from E2 v2, remain pending human approval, and are excluded
from model prompts. Requests explicitly specify local sources; this is not autonomous routing.

## Implementation

- Explicit opt-in Evidence snapshot export from the in-memory run ledger, including full source
  bodies, stable IDs, locators, and metadata. Default application runs remain content-free in
  telemetry and do not create the new snapshot. The ordinary trace is persisted before exporting
  optional content so an export failure does not discard the execution trace.
- Independent run/session IDs, preflight reference hash and anchor checks, a before/after corpus
  fingerprint, source/dataset manifests, per-task journals, and report/Evidence file hashes.
- Configured deep-report execution budget with **zero search queries and fetched pages**, plus
  a per-task 330-second outer watchdog. No Tavily calls are needed for this stage.
- Actual report text, application artifact paths, complete evidence snapshot, trace, reference
  rubric, and unchecked review worksheet are saved separately in ignored local results.
- Mechanical citation existence, missing/unknown citation IDs, observed source types, reference
  evidence retrieved, and reference evidence cited are distinct dimensions. They never automatically
  approve semantic correctness. No-answer abstention is also pending human review.

## Interpretation boundaries

The suite is a small development acceptance sample over the known E2 corpus, not an independent
test or a controlled retrieval ablation. Generation applies production retrieval/context limits;
E2's rank-only passage metrics must not be compared as if the experiment were identical. Anchor
coverage is a provisional diagnostic and does not assess entailment. Trace token instrumentation
is not complete provider billing. Knowledge-base scope is requested in the prompt; observed
local Evidence does not prove all attempted tools or access scopes were policy-enforced.

Saved Evidence bodies are sensitive artifacts and must stay under ignored local output paths.
Only content-free summaries should be committed. The new export is an internal opt-in argument,
not a new user-facing API or security feature.

An important review trap is that a degraded fallback can list **rejected** claim drafts whose
bracketed evidence IDs still resolve to actual records. The mechanical audit intentionally scans
all returned text and can therefore report reference IDs present while the application trace
correctly reports failed claim/final-report validation. These fields describe different checks;
neither should be collapsed into report acceptance or treated as contradictory measurements.

## Automated verification

Full regression: **229 passed, 6 skipped**. Changed-file Ruff lint and format checks pass.
New coverage includes opt-in/default-off export, preserving source bodies outside ordinary
telemetry, unknown citations, wrong-document anchors, retrieved-versus-cited evidence, no-answer
manual review, reference-hash rejection, exclusion of gold from prompts, real-run failure-package
persistence, sanitized exception categories, and actual returned report/evidence retention.

## Remaining E3 scope

Before paying for broader runs, address the observed local retrieval/abstention boundary and
compare against this preserved six-task baseline. Then add two web reports and two simple
cross-source reports, enforce at most ten Tavily queries for that batch, and perform the human
keypoint/claim review using the saved reports and passages.
No full report-answer accuracy, entailment pass rate, or independent reviewer approval is claimed.
E4 remains one improvement motivated by development failures, with a measured before/after.

Usage and file contract: [report acceptance README](../../evals/reports_acceptance/README.md).

## Actual local baseline, 2026-10-18

Run `report_acceptance_20261018T110328Z_58d089e350` executed all six tasks against real local
PostgreSQL/Qdrant retrieval and the configured `qwen-flash` model. All six returned nonempty
Markdown and saved Evidence snapshots/review packages. **Five runs degraded; only one had a
completed execution status, and that case collected no evidence. This is not a report pass rate.**
There were zero search queries and zero fetched pages. Before/after source, dataset, and corpus
checks passed. CLI exit status was 1 because degraded outcomes are not successful executions.

| Case | Execution | Seconds | Evidence records | All reference units retrieved/cited | Recorded failures |
| --- | --- | ---: | ---: | --- | --- |
| 001 scenarios | degraded | 140.828 | 11 | yes/yes | call limit; final citation validation |
| 002 advantages | degraded | 156.406 | 0 | no/no | timeout; upstream timeout |
| 003 AI customer service | degraded | 178.688 | 3 | yes/yes | timeout |
| 004 policy | degraded | 54.672 | 6 | no/no | final citation validation |
| 005 two-document comparison | completed | 20.453 | 0 | no/no | none recorded by runtime |
| 006 no-answer | degraded | 37.516 | 0 | not applicable | call limit; final citation validation |

Content-free record: [baseline summary](../../evals/reports/e3-1-local-reports-2026-10-18.json).
Full reports and source bodies remain only in ignored local run/session directories. Human review
is still pending for all six; no semantic acceptance or abstention score has been fabricated.

The baseline identifies actionable issues rather than a retrieval-score improvement:

1. The two-document task returned a report claiming documents were absent without making a
   `collect_evidence` call. Preflight had already verified those documents and reference passages.
   Case 002 also turned an execution/evidence gap into unsupported corpus-absence statements.
   Runtime completion must therefore not stand in for evidence-backed report acceptance.
2. Research still spends calls on `glob`, `ls`, `write_todos`, `write_file`, and attachment reads;
   these appear in the preserved tool counters even for local-only document tasks.
3. Cases 001 and 004 rejected all claim drafts. Inspection found bracket-wrapped IDs treated as
   unknown IDs, despite the underlying records being present. Future normalization must accept
   only an exact known-ID wrapper, never invent or fuzzy-match unknown evidence IDs.
4. Case 003 retrieved/cited the reference evidence but still timed out. Case 004 covered only one
   of its two policy units. Local-only report quality is consequently not solved by corpus presence
   or citation-ID existence alone.

The immediate next bounded change should require a real local Evidence lookup and distinguish
not-executed/error/no-evidence outcomes before allowing corpus-absence claims. Preserve the
claim-validation gate; use the saved development baseline for comparison instead of returning to
complex Hybrid recovery or tuning the exposed E2 query-test set.
