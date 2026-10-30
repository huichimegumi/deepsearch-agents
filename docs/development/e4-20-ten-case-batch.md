# E4.20 — Frozen ten-report batch

The next report baseline uses the six existing `local_v1` tasks and four existing
`extended_v1` tasks. The plan records both dataset hashes, all ten case IDs in
suite order, the local corpus hash, the extended asset lock hash, and the
scheduled Tavily ceiling of ten admitted queries. It validates the existing
local evidence anchors and the extended SQL/Web reference assets before saving.
The plan exposes no answer key to the Agent.

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.ten_case_batch `
  --lock evals/results/<extended_assets_run>/lock.json

.venv\Scripts\python.exe -m evals.reports_acceptance.run --execute
.venv\Scripts\python.exe -m evals.reports_acceptance.extended `
  --lock evals/results/<extended_assets_run>/lock.json --execute --allow-paid-search

.venv\Scripts\python.exe -m evals.reports_acceptance.ten_case_batch `
  --plan evals/results/<ten_case_plan_run>/plan.json `
  --local-results evals/results/<local_run>/results.json `
  --extended-results evals/results/<extended_run>/results.json
```

The summary requires all ten results in frozen order, real execution flags,
unchanged inputs, the same source hash and model across the two runs, the
ordinary local route, and the default extended researcher. It verifies the
saved report and Evidence file hashes. Degraded, timed-out, and error rows
remain in the denominator and retain their failure reasons. It reports
execution status, finite reference-unit retrieval/citation, citation-ID
resolution, observed model calls, elapsed time, and admitted searches.

These mechanical columns do not establish factual accuracy or claim support.
The summary keeps answer accuracy null and human acceptance pending. Private
source passages and model text stay in ignored `evals/results/` directories;
only a content-free reviewed result may be published under `evals/reports/`.
The 12-call application setting has historically been exceeded by observed
instrumented calls, so that setting must not be described as a verified hard
provider billing limit.

## Current-version execution, 2026-10-30

The plan is `ten_case_plan_20261030T075526Z_902254a746`; the completed runs
are `report_acceptance_20261030T075549Z_b11bd7a238` and
`extended_reports_20261030T080951Z_5008c43ce0`. Both report unchanged inputs,
the same application/evaluation source hash and configured `qwen-flash`. The
validated, content-free [summary](../../evals/reports/e4-20-ten-case-baseline-2026-10-30.json)
is derived from `ten_case_summary_20261030T082056Z_d75a03db1a`. Each runner
returned exit code 1 because degraded cases remain present. The batch summary
itself succeeded and contains all ten frozen IDs.

| Task | Execution | Seconds | Evidence records | All finite units retrieved / cited |
| --- | --- | ---: | ---: | --- |
| local 001 | completed | 71.75 | 6 | yes / yes |
| local 002 | degraded | 193.62 | 10 | yes / yes |
| local 003 | degraded | 210.58 | 11 | yes / no |
| local 004 | completed | 80.55 | 6 | no / no |
| local 005 | degraded | 98.36 | 2 | no / no |
| local 006, no-answer | degraded | 157.97 | 0 | separate abstention review |
| Web 001 | degraded | 184.94 | 3 | yes / yes |
| Web 002 | degraded | 215.78 | 3 | no / no |
| cross 001, local + Web | degraded | 189.62 | 9 | no / no |
| cross 002, SQL + local | completed | 47.58 | 2 | no / no |

Three executions completed and seven degraded. Median elapsed time was
**171.453 seconds** across ten one-shot tasks. The expanded four-task run
admitted exactly **10 Tavily queries**: 3, 3, 4, and 0 by task. This is an
admission count, not an independent credit invoice. All ten rows have report
and Evidence snapshots; the summary verifies their hashes. Web 001 retrieved
and cited all of its finite reference units but still degraded after an
upstream model timeout, showing why retrieval coverage and execution status
must be reported separately. Local 003 and Web 002 also record final-report
and Claim-fallback citation validation failures. Cross 001 records exhausted
subagent retrieval budget. The no-answer task retrieved zero records and
degraded; appropriateness of its wording is pending review.

These are mechanical observations. In particular, cross 002's `completed`
status does not establish that its SQL result and local scenario explanation
answer the task correctly. AI source-based triage and human claim/keypoint
review are the next stage; generative accuracy remains null. The result table
provides a single current-version baseline for selecting one frequent failure
to improve, while the older E3 runs remain separate historical measurements.
