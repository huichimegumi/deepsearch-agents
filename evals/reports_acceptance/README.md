# E3.1: local report acceptance

E3.4 exposes the **default-off** `--indexed-local` experiment: no researcher filesystem/todo/
memory/delegation tools, a local-only wrapper retaining the `collect_evidence` name, and two
supplemental tool requests. Both bounded tasks degraded and the negative still overclaimed corpus
absence; do not promote timing or valid IDs into quality acceptance. Default generation, attachments,
and other source routes remain on the prior researcher. See the [pilots and release gate](../../docs/development/e3-4-indexed-local-agent.md).

E3.3 adds a production local-filename delivery boundary and saves independent
`local_source_reference_checks`. `python -m evals.reports_acceptance.replay_sources
--report-results ... --case-id ...` replays only filename identity over saved artifacts, without
generation, database, retrieval, or web calls. Withheld notices are not supported answers or
automatically correct refusals. See the [policy scope and validation](../../docs/development/e3-3-local-source-provenance.md).

E3.2 adds `python -m evals.reports_acceptance.support_review --report-results ... --case-id ...`.
Default output is a full readable human worksheet with actual report paragraphs and source
passages, without a model call. Optional model suggestions fail closed on invented quotes,
uncited sources, missing/duplicate units, or timeout. Selected-segment scope cannot grade whole
report coverage/abstention. All six real model pilot invocations were invalid: do not use this
configured judge for automatic acceptance. See the [contract, private packet paths, and pilot](../../docs/development/e3-2-evidence-support-review.md).

E3.1b narrowly normalizes one bracket-wrapped, already eligible stable Claim ID. Evaluation
snapshots now additionally retain original typed `claim_validation_batches` for offline
exact-string versus canonical-policy replay. No semantic approval follows from either policy.
See the [policy and replay contract](../../docs/development/e3-1b-canonical-claim-references.md).

E3.1a adds required production lookup for local-only requests and preserves `local_retrieval`
states in each row. Zero-local-Evidence compression/writing is replaced with a deterministic
not-executed/error/no-evidence report; a returned record still needs normal Claim/citation and
human semantic checks. See the [boundary contract](../../docs/development/e3-1a-required-local-retrieval.md).

The real paired six-task run reduced answerable cases with zero local records from 2/5 to 0/5,
but three tasks still degraded. Every final row had records: the negative task's later broader
queries found unrelated passages, and its document-inventory statements were unsupported.
The zero-record terminal override is verified by deterministic integration tests, not by treating
this real negative report as a passing refusal. See the [paired summary](../reports/e3-1a-local-retrieval-2026-10-19.json).

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
