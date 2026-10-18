# E3.1: local report acceptance

This runs the real research workflow, not a filename/routing baseline. Six development tasks
reuse source-verified, still human-unapproved E2 references: four single-document tasks,
one two-document task, and one unavailable-answer task. This is not a new held-out test.
The JSON suite pins the reference file's byte hash and lists the exact selected question IDs.
Labels and anchors never enter the Agent prompt. The user-visible request explicitly limits
the report to named local knowledge bases; it is not autonomous source-routing evaluation.

```powershell
# Preflight: checks the reference hash and every anchor against the live indexed corpus.
.venv\Scripts\python.exe -m evals.reports_acceptance.run
# Real configured LLM calls; local embedding/reranking; zero web query/page budgets.
.venv\Scripts\python.exe -m evals.reports_acceptance.run --execute
# Explicit small subset, also recorded in the manifest:
.venv\Scripts\python.exe -m evals.reports_acceptance.run --execute --case-id report_local_005
```

Each invocation gets a fresh run/session and preserves earlier outputs. Defaults use the
configured deep-report budget, except search queries and fetched pages are zero. There is a
330-second outer watchdog per task. Timeout/degraded/error and missing-trace outcomes remain
visible rather than being converted into successful report acceptance. CLI exit status reports
execution/input drift only, not semantic acceptance. Preflight makes no generative LLM calls.

## Private review package

Under ignored `evals/results/<run_id>/<case_id>/`:

- `report.md`: the actual returned final report, including a degraded result when applicable.
- `evidence.json`: complete deduplicated Evidence records, including content and source locators.
- `trace.json`: execution state and instrumented resource usage, **not total provider billing**.
- `reference.json`: keypoints, source hashes, alternative literal anchors, and answerability.
- `REVIEW.md`: unchecked human review worksheet for keypoints, claims, and appropriate abstention.

`results.json` contains the execution manifest, corpus hash, per-case outcomes, artifact paths,
report/evidence hashes, and mechanical checks. It is journaled after every task. Source, suite,
and corpus drift are checked after the batch. Returned report presence and application artifact
paths are separate fields. Ordinary application invocations do not write Evidence bodies:
`run_deep_agent(export_evaluation_evidence=True)` explicitly opts into a content-bearing
session artifact; it does not add source content to telemetry or expose a new HTTP API flag.

**These files contain local document excerpts and potentially private SQL/web content.** Keep
them local; do not commit or publish the review package. Only sanitized, content-free summaries
belong under `evals/reports/`. The evidence export has the same filesystem access boundary as
the existing session reports, not a new encryption or local-model guarantee.

## What the checks mean

The audit separately reports snapshot presence, source types, citation IDs that resolve to
saved records, unknown IDs, and which reference evidence units were retrieved versus cited.
Repeated chunks do not inflate a unit's coverage; a correct literal anchor in the wrong document
is not credited. Coverage uses E2's finite anchor alternatives and can still have false negatives.
Production retrieval thresholds/context limits apply here; this is not E2 rank-only Recall@5.

A citation ID that exists does not establish that a claim follows from its passage. Finding all
reference anchors somewhere in cited records does not establish that the report answers every
keypoint correctly. A no-answer report needs semantic review even if it cites nothing. Accordingly
answer accuracy is null and acceptance/entailment/keypoint correctness remain pending human review.
The scanner includes IDs in rejected-claim appendices and degraded fallbacks: such IDs can resolve
even when the application's stricter accepted-Claim citation validation fails. Inspect execution
status, trace failure reasons, and the report body together; do not count these as passing reports.
The local-source check observes emitted Evidence types; it is not a complete audit of every
attempted tool call or proof that requested knowledge-base scope was enforced by an access policy.

The first real six-task run produced five degraded executions and one completed execution with
no collected Evidence; all six produced files, which is not acceptance. See the
[baseline and findings](../../docs/development/e3-1-local-report-acceptance.md).

Next: require real local retrieval and separate execution failure from no-evidence before broader
runs. Remaining E3 work adds two bounded web and two simple cross-source reports, with a batch-wide
Tavily budget of at most ten queries, and human claim/keypoint review. Do not tune complex
Hybrid recovery or claim full E3 completion from the local execution stage alone.
